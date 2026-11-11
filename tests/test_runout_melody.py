"""HH v3/v4 common runout contract; never infer from sensor drops or pause text."""
from unittest import TestCase
from unittest.mock import Mock
from petrel.moonraker.subscription import MoonrakerSubscription
from petrel.ui.events import InputEvent


class RunoutMelodyTests(TestCase):
    def make(self, runout=False, enabled=True, **fields):
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        callback = Mock()
        sub.set_melody_callback(callback)
        sub._merge({'mmu':dict(enabled=enabled,runout=runout,**fields),
                    'print_stats':{'state':'printing'}},1,replace=True)
        sub._state = 'ready'
        sub.request = Mock()
        return sub,callback

    def update(self, sub, values, time):
        sub._notification({'method':'notify_status_update','params':[values,time]})

    def test_shared_v3_v4_flag_once_with_endless_spool_and_no_new_requests(self):
        # v3/v4 expose the same fields; no version string is required.
        sub,callback = self.make(operation='toolchange',action='Unloading')
        self.update(sub,{'mmu':{'runout':True,'operation':'runout'}},2)
        self.update(sub,{'mmu':{'runout':True,'action':'Loading'}},3)
        self.update(sub,{'mmu':{'action':'Idle','runout':False}},4)
        callback.assert_called_once_with('FILAMENT_OUT',0)
        sub.request.assert_not_called()
        self.update(sub,{'mmu':{'runout':True}},5)
        self.assertEqual(callback.call_count,2)

    def test_normal_changes_clog_gate_empty_and_reason_text_are_not_triggers(self):
        sub,callback = self.make()
        for index,values in enumerate((
            {'operation':'toolchange','action':'Unloading','sensors':{'gate':False}},
            {'operation':'load','action':'Loading'},
            {'operation':'unload','gate_status':[0,1,1,1]},
            {'operation':'runout','runout':False,'reason_for_pause':'A clog/tangle was detected'},
            {'reason_for_pause':'Runout detected on gate'}),2):
            self.update(sub,{'mmu':values},index)
        callback.assert_not_called()

    def test_initial_reconnect_disabled_invalid_and_missing_flags_are_silent(self):
        for value in (True,None,1,0,'true',[],{}):
            sub,callback = self.make(runout=value)
            self.update(sub,{'mmu':{'runout':True}},2)
            callback.assert_not_called()
        sub,callback = self.make()
        sub._status['mmu'].pop('runout')
        self.update(sub,{'mmu':{'runout':True}},2)
        callback.assert_not_called()
        sub,callback = self.make(enabled=False)
        self.update(sub,{'mmu':{'runout':True}},2)
        self.update(sub,{'mmu':{'enabled':True}},3)
        callback.assert_not_called()
        sub,callback = self.make()
        self.update(sub,{'mmu':{'operation':'runout'}},2)
        callback.assert_not_called()
        sub._invalidate('lost')
        sub._merge({'mmu':{'enabled':True,'runout':True}},3,replace=True)
        sub._state = 'ready'
        self.update(sub,{'mmu':{'runout':True}},4)
        callback.assert_not_called()
        self.update(sub,{'mmu':{'runout':False}},5)
        self.update(sub,{'mmu':{'runout':True}},4.5)  # stale packet
        callback.assert_not_called()
        self.update(sub,{'mmu':{'runout':True}},6)
        callback.assert_called_once_with('FILAMENT_OUT',sub._epoch)

    def test_pause_is_covered_by_runout_but_error_keeps_priority(self):
        sub,callback = self.make()
        self.update(sub,{'mmu':{'runout':True},'print_stats':{'state':'paused'}},2)
        callback.assert_called_once_with('FILAMENT_OUT',0)
        sub,callback = self.make()
        self.update(sub,{'mmu':{'runout':True}},2)
        self.update(sub,{'print_stats':{'state':'paused'}},3)
        callback.assert_called_once_with('FILAMENT_OUT',0)
        sub,callback = self.make()
        self.update(sub,{'mmu':{'runout':True},'print_stats':{'state':'error'}},2)
        callback.assert_called_once_with('ERROR',0)
        sub,callback = self.make()
        self.update(sub,{'print_stats':{'state':'paused'}},2)
        callback.assert_called_once_with('PAUSE',0)

    def test_owner_uses_shared_volume_and_rejects_stale_runout(self):
        from test_buzzer_events import MelodyOwnerTests
        view = MelodyOwnerTests().make()
        view._event_buzzer_ready = True
        view._process_input_untraced(InputEvent('melody_FILAMENT_OUT',0,8))
        args=view._buzzer_player.play_melody.call_args
        self.assertEqual(args.args[0],'FILAMENT_OUT')
        self.assertEqual(args.args[1].volume,30)
        view._buzzer_player.reset_mock()
        view._process_input_untraced(InputEvent('melody_FILAMENT_OUT',0,7))
        view._buzzer_player.play_melody.assert_not_called()
