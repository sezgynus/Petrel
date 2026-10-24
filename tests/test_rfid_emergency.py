"""Emergency tag enrollment and home navigation regressions (no hardware)."""
from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from nfc_core import NFCCore
from test_nfc_core import backend
from test_capabilities import display, printer, snapshot
from test_regressions import backend as printer_backend


class EmergencyTagTests(unittest.TestCase):
    def press(self, view, selection=None):
        if selection is not None:
            view._rfid_selection = selection
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.HMI_RFID()

    def test_info_is_always_last_with_optional_leveling(self):
        view = display(snapshot())
        for leveling in ([], [('BACK', 'Back', 0), ('HOME', 'Home', 1)]):
            view._leveling_menu_entries = Mock(return_value=leveling)
            keys = [row[0] for row in view._home_entries()]
            self.assertEqual(keys[-2:], ['RFID', 'INFO'])
            self.assertEqual(keys.count('INFO'), 1)

    def test_enrollment_confirmation_cancel_replace_remove_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = backend()
            stop = Mock(return_value=Future())
            core = NFCCore(reader, emergency_stop=stop,
                           actions_file=Path(tmp) / 'actions.json')
            emit = reader.set_event_sink.call_args.args[0]
            view = display(snapshot())
            view.pd.get_nfc_core = Mock(return_value=core)
            view.checkkey = view.RFIDMenu
            view._uart_online = True
            view._queue_nfc_ui_event = Mock()
            view.Draw_RFID_Menu = Mock()
            self.press(view, 1)  # Open emergency-tag settings.
            self.press(view, 1)  # Capture next arrival.
            self.assertEqual(view._rfid_mode, 'waiting')
            emit('card.detected', {'uid': '01:02:03:04'})
            view._queue_nfc_ui_event.assert_called_with('nfc_emg_capture')
            view._rfid_assignment_event()
            self.assertEqual(view._rfid_mode, 'confirm')
            self.assertIsNone(core.global_action_uid('emergency_stop'))
            self.press(view, 0)  # Discard candidate.
            self.assertIsNone(core.global_action_uid('emergency_stop'))
            self.press(view, 1)
            emit('card.detected', {'uid': '05:06:07:08'})
            view._rfid_assignment_event()
            self.press(view, 1)  # Explicit save.
            self.assertEqual(core.global_action_uid('emergency_stop'), '05:06:07:08')
            stop.assert_not_called()
            emit('card.detected', {'uid': '05:06:07:08'})
            stop.assert_called_once_with()
            restored = NFCCore(backend(), actions_file=Path(tmp) / 'actions.json')
            self.assertEqual(restored.global_action_uid('emergency_stop'), '05:06:07:08')
            restored.close()
            self.press(view, 1)  # Replace.
            emit('card.detected', {'uid': '09:0A'})
            view._rfid_assignment_event()
            self.press(view, 1)
            self.assertEqual(core.global_action_uid('emergency_stop'), '09:0A')
            self.press(view, 2)  # Remove.
            self.assertIsNone(core.global_action_uid('emergency_stop'))
            self.press(view, 1)  # Waiting can be cancelled.
            pending = view._rfid_assignment
            self.press(view, 0)
            self.assertTrue(pending.cancelled())
            emit('card.detected', {'uid': '0B:0C'})
            self.assertIsNone(core.global_action_uid('emergency_stop'))
            core.close()

    def test_reenrollment_of_saved_card_captures_without_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader, stop = backend(), Mock()
            core = NFCCore(reader, emergency_stop=stop,
                           actions_file=Path(tmp) / 'actions.json')
            core.assign_global_action('emergency_stop', 'AA:BB')
            emit = reader.set_event_sink.call_args.args[0]
            ordinary = Mock()
            core.subscribe('card.detected', ordinary, priority=500)
            pending = core.begin_assignment(action='emergency_stop')
            emit('card.detected', {'uid': 'AA:BB'})
            self.assertEqual(pending.result()['uid'], 'AA:BB')
            stop.assert_not_called()
            ordinary.assert_called_once()
            core.assign_global_action('emergency_stop', pending.result()['uid'])
            emit('card.detected', {'uid': 'AA:BB'})
            stop.assert_called_once()
            self.assertEqual(ordinary.call_count, 1)
            # Spool enrollment must still respect emergency priority.
            pending = core.begin_assignment()
            emit('card.detected', {'uid': 'AA:BB'})
            self.assertFalse(pending.done())
            self.assertEqual(stop.call_count, 2)
            pending.cancel()
            pending = core.begin_assignment(action='emergency_stop')
            pending.cancel()
            emit('card.detected', {'uid': 'AA:BB'})
            self.assertEqual(stop.call_count, 3)
            core.close()

    def test_card_feedback_observes_both_enrollment_flows_once(self):
        from ui_events import InputEvent
        with tempfile.TemporaryDirectory() as tmp:
            reader = backend()
            core = NFCCore(reader, actions_file=Path(tmp) / 'actions.json')
            view = display(snapshot())
            view._closed = False
            view._uart_online = False
            view._queue_nfc_ui_event = Mock(return_value=False)
            view._rfid_buzzer_feedback = Mock()
            view._nfc_share_component = Mock()
            view._nfc_share_component.return_value.sync.return_value = False
            view.pd.sync_nfc_event = Mock()
            view._subscribe_nfc_card_notifications(core)
            emit = reader.set_event_sink.call_args.args[0]
            for action in ('emergency_stop', None):
                view._queue_nfc_ui_event.reset_mock()
                pending = core.begin_assignment(action=action)
                view.checkkey = view.RFIDMenu
                view._rfid_mode = 'waiting' if action else 'spool_waiting'
                view._rfid_assignment = pending
                emit('card.detected', {'uid': 'AA:BB'})
                self.assertTrue(pending.done())
                view._queue_nfc_ui_event.assert_called_once_with('nfc_card')
                view._process_input_untraced(InputEvent('nfc_card', 0, 0, 0))
                self.assertEqual(view._rfid_buzzer_feedback.call_count, 0 if action else 1)
                view._rfid_assignment_event()
            self.assertEqual(view._rfid_buzzer_feedback.call_count, 2)
            core.close()

    def test_remove_row_disappears_and_selection_returns_to_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = NFCCore(backend(), actions_file=Path(tmp) / 'actions.json')
            core.assign_global_action('emergency_stop', 'AA:BB')
            view = display(snapshot())
            view.pd.get_nfc_core = Mock(return_value=core)
            view._rfid_mode = 'emg'
            view._draw_list_menu = Mock()
            view.Draw_RFID_Menu()
            self.assertIn('Remove tag', [r[0] for r in view._draw_list_menu.call_args.args[1]])
            self.press(view, 2)
            self.assertIsNone(core.global_action_uid('emergency_stop'))
            self.assertNotIn('Remove tag', [r[0] for r in view._draw_list_menu.call_args.args[1]])
            self.assertEqual(view._rfid_selection, 0)
            view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_CW)
            view._rotation_steps = 8
            view.HMI_RFID()
            self.assertEqual(view._rfid_selection, 1)
            core.close()

    def test_disabled_reader_cannot_begin_enrollment(self):
        view = display(snapshot())
        view.pd.get_nfc_core = Mock(return_value=None)
        view._rfid_mode = 'emg'
        view.Draw_RFID_Menu = Mock()
        self.press(view, 1)
        self.assertEqual(view._rfid_mode, 'emg')
        self.assertIn('unavailable', view._rfid_message)

    def test_real_printer_core_uses_emergency_rpc_without_idle_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = printer(snapshot())
            pd.subscription.request.return_value = Future()
            with patch.object(printer_backend, 'installed_enabled', return_value=True), \
                    patch('nfc_core.settings_path', return_value=Path(tmp) / 'settings.json'):
                core = pd.get_nfc_core()
            core.assign_global_action('emergency_stop', 'AA:BB')
            # This goes directly through the existing prioritized emergency RPC
            # path; no G-code queue and no UI/print-idle precondition.
            pd._rfid_reader.set_event_sink.call_args.args[0](
                'card.detected', {'uid': 'AA:BB'})
            pd.subscription.request.assert_called_once_with('printer.emergency_stop')
            core.close()

    def test_emergency_card_alarms_directly_even_when_klipper_rpc_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = backend()
            stop = Mock(side_effect=ConnectionError('Klipper already disconnected'))
            core = NFCCore(reader, emergency_stop=stop,
                           actions_file=Path(tmp) / 'actions.json')
            view = display(snapshot())
            view._buzzer_player = Mock()
            settings = type(view._buzzer_settings())
            view._buzzer_values = settings(enabled=True, volume=0, click=0, encoder=0)
            view._subscribe_emergency_buzzer(core)
            emit = reader.set_event_sink.call_args.args[0]
            emit('card.detected', {'uid': '01:02'})
            view._buzzer_player.play_emergency.assert_not_called()
            core.assign_global_action('emergency_stop', 'AA:BB')
            emit('card.detected', {'uid': 'AA:BB'})
            stop.assert_called_once_with()
            view._buzzer_player.play_emergency.assert_called_once_with()
            view._buzzer_player.play.assert_not_called()
            # Even though the alarm ignores volume/tone=Off, the explicit
            # master Buzzer Off setting must suppress subsequent alerts.
            view._buzzer_values = settings(enabled=False, volume=100)
            emit('card.detected', {'uid': 'AA:BB'})
            self.assertEqual(stop.call_count, 2)
            view._buzzer_player.play_emergency.assert_called_once_with()
            core.close()

    def test_rfid_home_artwork_is_distinct_and_both_states_are_bound(self):
        from lcd_resources import ICON_RFID_HOME_NORMAL, ICON_RFID_HOME_SELECTED
        from PIL import Image, ImageChops
        view = display(snapshot())
        entry = next(row for row in view._home_entries() if row[0] == 'RFID')
        self.assertEqual(entry[1], 'NFC')
        self.assertEqual(entry[2:], (ICON_RFID_HOME_NORMAL, ICON_RFID_HOME_SELECTED))
        self.assertNotEqual(entry[2:], (view.ICON_Info_0, view.ICON_Info_1))
        root = Path(__file__).resolve().parents[1] / 'assets/icons'
        for number in entry[2:]:
            with Image.open(root / f'{number:03d}.jpg') as icon:
                self.assertEqual(icon.size, (110, 100))
                with Image.open(root / '055.jpg') as info:
                    self.assertIsNotNone(ImageChops.difference(icon, info).getbbox())

    def test_rfid_actions_and_all_uid_lines_stay_above_dashboard(self):
        view = display(snapshot())
        view.pd.sync_nfc_event = Mock()
        uid = ':'.join(f'{i:02X}' for i in range(32))
        view.pd.system_info['rfid'] = {
            'status': 'Listening', 'card': {'uid': uid, 'type': 'ISO14443A'}}
        core = Mock()
        core.global_action_uid.return_value = uid
        view.pd.get_nfc_core = Mock(return_value=core)
        view._draw_list_menu = Mock()
        view._draw_menu_text = Mock()
        view._rfid_candidate = {'uid': uid}
        for mode in ('info', 'emg', 'confirm'):
            with self.subTest(mode=mode):
                view._rfid_mode = mode
                view._draw_menu_text.reset_mock()
                view.Draw_RFID_Menu()
                labels = [row[0] for row in view._draw_list_menu.call_args.args[1]]
                if mode == 'info':
                    self.assertEqual(labels, ['Back', 'Emergency stop tag', 'Spoolman tag'])
                if mode == 'emg':
                    self.assertEqual(labels, ['Back', 'Replace tag', 'Remove tag'])
                calls = view._draw_menu_text.call_args_list
                self.assertTrue(calls)
                self.assertTrue(all(call.args[2] + 16 < view.STATUS_Y for call in calls))
                lines = [call.args[0] for call in calls if ':' in call.args[0]]
                self.assertEqual(':'.join(lines), uid)

