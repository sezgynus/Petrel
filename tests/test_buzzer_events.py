"""Live transition notifications, bootstrap silence and bounded owner delivery."""
from unittest import TestCase
from unittest.mock import Mock

from moonraker_subscription import MoonrakerSubscription
from moonraker_client import MoonrakerError
from test_regressions import ui

Settings = ui.BuzzerSettings
from ui_events import InputEvent
from test_capabilities import display, snapshot
from test_subscription import FakeSocket


class MelodyEventTests(TestCase):
    def make(self, initial='printing'):
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        observer = Mock()
        sub.set_melody_callback(observer)
        sub._merge({'print_stats': {'state': initial}, 'webhooks': {'state': 'ready'}}, 1, replace=True)
        sub._state = 'ready'
        return sub, observer

    def change(self, sub, state, time):
        sub._notification({'method': 'notify_status_update',
                           'params': [{'print_stats': {'state': state}}, time]})

    def test_actual_websocket_transitions_once_without_requests(self):
        sub, observer = self.make()
        sub.request = Mock()
        self.change(sub, 'paused', 2)
        self.change(sub, 'paused', 3)
        sub._merge({'extruder': {'temperature': 180}}, 4)
        self.change(sub, 'printing', 5)
        self.change(sub, 'complete', 6)
        self.change(sub, 'complete', 7)
        self.assertEqual([c.args for c in observer.call_args_list],
                         [('PAUSE', 0), ('RESUME', 0), ('PRINT_DONE', 0)])
        sub.request.assert_not_called()

    def test_cancel_start_bootstrap_and_reconnect_do_not_replay(self):
        sub, observer = self.make('standby')
        self.change(sub, 'printing', 2)
        self.change(sub, 'cancelled', 3)
        self.change(sub, 'standby', 4)
        observer.assert_not_called()
        for initial in ('complete', 'paused', 'error'):
            sub._invalidate('Disconnected')
            sub._socket = FakeSocket(snapshot={
                'toolhead': {}, 'gcode_move': {}, 'virtual_sdcard': {},
                'print_stats': {'state': initial}, 'webhooks': {'state': 'ready'}})
            sub._bootstrap()
        observer.assert_not_called()
        # Reconnect to paused establishes a baseline; a later resume is real.
        sub._invalidate('Disconnected')
        sub._merge({'print_stats': {'state': 'paused'}}, 30, replace=True)
        sub._state = 'ready'
        self.change(sub, 'printing', 31)
        observer.assert_called_once_with('RESUME', sub._epoch)

    def test_shutdown_and_print_error_share_one_alarm_until_new_job(self):
        sub, observer = self.make()
        self.change(sub, 'error', 2)
        with self.assertRaises(MoonrakerError):
            sub._notification({'method': 'notify_klippy_shutdown', 'params': []})
        sub._merge({'webhooks': {'state': 'shutdown'}}, 3)
        observer.assert_called_once_with('ERROR', 0)
        sub._merge({'webhooks': {'state': 'ready'}, 'print_stats': {'state': 'printing'}}, 4)
        self.change(sub, 'error', 5)
        self.assertEqual(observer.call_count, 2)

    def test_shutdown_only_and_disconnect_are_distinct(self):
        sub, observer = self.make()
        with self.assertRaises(MoonrakerError):
            sub._notification({'method': 'notify_klippy_disconnected', 'params': []})
        observer.assert_not_called()
        with self.assertRaises(MoonrakerError):
            sub._notification({'method': 'notify_klippy_shutdown', 'params': []})
        observer.assert_called_once_with('ERROR', 0)

    def test_stale_deltas_and_subscribe_updates_cannot_emit(self):
        sub, observer = self.make()
        sub._subscribing = True
        self.change(sub, 'paused', 2)
        sub._subscribing = False
        self.change(sub, 'printing', 1.5)  # Ignored stale delta.
        observer.assert_not_called()
        sub.set_melody_callback(None)
        self.change(sub, 'printing', 3)
        observer.assert_not_called()

    def test_bad_observer_does_not_break_status_transport(self):
        sub, _ = self.make()
        sub.set_melody_callback(Mock(side_effect=RuntimeError('Audio unavailable')))
        self.change(sub, 'paused', 2)
        self.assertEqual(sub.snapshot()['status']['print_stats']['state'], 'paused')


class MelodyOwnerTests(TestCase):
    def make(self):
        view = display(snapshot())
        view._closed = False
        view._buzzer_player = Mock()
        view._buzzer_values = Settings(volume=30)
        view._loop = Mock()
        view.pd.subscription.lifecycle.return_value = {'state': 'ready', 'epoch': 8}
        return view

    def test_boot_arms_once_after_preferences_and_respects_volume(self):
        view = self.make()
        view._queue_buzzer_melody('PAUSE', 8)
        view._loop.post_coalesced.assert_not_called()
        view._arm_buzzer_events()
        view._buzzer_player.play_melody.assert_called_once_with('BOOT', Settings(volume=30), priority=True)
        view._event_buzzer_ready = False
        view._arm_buzzer_events()
        self.assertEqual(view._buzzer_player.play_melody.call_count, 1)
        view._buzzer_values = Settings(enabled=False)
        view._event_buzzer_melody('PRINT_DONE')
        self.assertEqual(view._buzzer_player.play_melody.call_count, 1)

    def test_events_are_queued_and_stale_reconnected_events_drop(self):
        view = self.make()
        view._event_buzzer_ready = True
        view._queue_buzzer_melody('PAUSE', 8)
        event = view._loop.post_coalesced.call_args.args[0]
        self.assertEqual((event.kind, event.epoch), ('melody_PAUSE', 8))
        view._process_input_untraced(event)
        self.assertEqual(view._buzzer_player.play_melody.call_args.args[0], 'PAUSE')
        view._buzzer_player.reset_mock()
        for name in ('PRINT_DONE', 'RESUME', 'ERROR'):
            view._process_input_untraced(InputEvent('melody_' + name, 0, 7))
        view._buzzer_player.play_melody.assert_not_called()
        view.pd.subscription.lifecycle.return_value = {'state': 'disconnected', 'epoch': 9}
        view._process_input_untraced(InputEvent('melody_ERROR', 0, 8))
        self.assertEqual(view._buzzer_player.play_melody.call_args.args[0], 'ERROR')
        view._closed = True
        view._buzzer_player.reset_mock()
        view._process_input_untraced(InputEvent('melody_ERROR', 0, 8))
        view._buzzer_player.play_melody.assert_not_called()

    def test_shutdown_sound_only_on_confirmed_request_once(self):
        from test_power_shortcut import PowerShortcutTests
        view = PowerShortcutTests().view()
        view.checkkey = view.PowerConfirm
        view._power_hold_popup = True
        view._power_shutdown_requested = False
        view._power_confirm_yes = True
        view._power_block_reason = Mock(return_value=None)
        view._event_buzzer_melody = Mock()
        view._show_message = Mock()
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view._handle_power_navigation()
        view._handle_power_navigation()
        view._event_buzzer_melody.assert_called_once_with('SHUTDOWN')
        view.pd.power_off_if_on.assert_called_once()
        view._power_shutdown_requested = False
        view._power_confirm_yes = False
        view._event_buzzer_melody.reset_mock()
        view._restore_power_origin = Mock()
        view._handle_power_navigation()
        view._event_buzzer_melody.assert_not_called()
