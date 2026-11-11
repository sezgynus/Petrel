"""Layer notifications use live reported deltas, never queries or Z inference."""
from unittest import TestCase
from unittest.mock import Mock
from petrel.moonraker.subscription import MoonrakerSubscription
from petrel.ui.events import InputEvent


class LayerMelodyTests(TestCase):
    def make(self, state='printing', layer=3):
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        callback = Mock()
        sub.set_melody_callback(callback)
        sub._merge({'print_stats':{'state':state,'filename':'part.gcode',
                                  'info':{'current_layer':layer,'total_layer':50}}},1,replace=True)
        sub._state = 'ready'
        sub.request = Mock()
        return sub, callback

    def update(self, sub, fields, time):
        sub._notification({'method':'notify_status_update','params':[{'print_stats':fields},time]})

    def test_forward_layer_once_and_no_extra_queries(self):
        sub, callback = self.make()
        self.update(sub, {'info':{'current_layer':4}},2)
        self.update(sub, {'info':{'current_layer':4}},3)
        self.update(sub, {'info':{'current_layer':9}},4)
        self.assertEqual([c.args[0] for c in callback.call_args_list], ['LAYER_CHANGE']*2)
        sub.request.assert_not_called()

    def test_invalid_missing_decreasing_layers_and_nonlayer_fields_are_silent(self):
        for value in (None, True, '4', 4.0, -1, 0, 2):
            sub, callback = self.make()
            self.update(sub, {'info':{'current_layer':value}},2)
            callback.assert_not_called()
        sub, callback = self.make()
        self.update(sub, {'info':{'total_layer':100}},2)
        sub._merge({'toolhead':{'position':[0,0,20,0]}},3)
        callback.assert_not_called()
        sub, callback = self.make()
        self.update(sub, {'info':{'current_layer':51,'total_layer':50}},2)
        callback.assert_not_called()

    def test_first_value_job_start_change_and_reset_are_baselines(self):
        sub, callback = self.make(layer=None)
        self.update(sub, {'info':{'current_layer':1}},2)
        callback.assert_not_called()
        self.update(sub, {'info':{'current_layer':2}},3)
        callback.assert_called_once_with('LAYER_CHANGE',0)
        sub, callback = self.make(state='standby',layer=0)
        self.update(sub, {'state':'printing','info':{'current_layer':1}},2)
        callback.assert_not_called()
        self.update(sub, {'filename':'other.gcode','info':{'current_layer':4}},3)
        callback.assert_not_called()
        self.update(sub, {'info':{'current_layer':1}},4)
        callback.assert_not_called()
        self.update(sub, {'info':{'current_layer':2}},5)
        callback.assert_called_once_with('LAYER_CHANGE',0)

    def test_pause_resume_bootstrap_stale_and_reconnect_do_not_sound_layers(self):
        sub, callback = self.make()
        self.update(sub, {'state':'paused','info':{'current_layer':4}},2)
        self.update(sub, {'state':'printing','info':{'current_layer':5}},3)
        self.assertEqual([c.args[0] for c in callback.call_args_list], ['PAUSE','RESUME'])
        callback.reset_mock()
        self.update(sub, {'info':{'current_layer':6}},2.5)
        callback.assert_not_called()
        sub._invalidate('lost')
        sub._merge({'print_stats':{'state':'printing','filename':'part.gcode',
                                  'info':{'current_layer':20}}},4,replace=True)
        sub._state = 'ready'
        self.update(sub, {'info':{'current_layer':20}},5)
        callback.assert_not_called()
        self.update(sub, {'info':{'current_layer':21}},6)
        callback.assert_called_once_with('LAYER_CHANGE',sub._epoch)

    def test_owner_routes_layer_sound_through_shared_player_and_volume(self):
        from test_buzzer_events import MelodyOwnerTests
        view = MelodyOwnerTests().make()
        view._event_buzzer_ready = True
        view._process_input_untraced(InputEvent('melody_LAYER_CHANGE',0,8))
        args = view._buzzer_player.play_melody.call_args
        self.assertEqual(args.args[0],'LAYER_CHANGE')
        self.assertEqual(args.args[1].volume,30)
        self.assertTrue(args.kwargs['priority'])
