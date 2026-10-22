"""Emergency tag enrollment and home navigation regressions (no hardware)."""
from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from nfc_core import NFCCore
from test_nfc_core import backend
from test_capabilities import display, printer, snapshot


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
            with patch('printerInterface.installed_enabled', return_value=True), \
                    patch('nfc_core.settings_path', return_value=Path(tmp) / 'settings.json'):
                core = pd.get_nfc_core()
            core.assign_global_action('emergency_stop', 'AA:BB')
            # This goes directly through the existing prioritized emergency RPC
            # path; no G-code queue and no UI/print-idle precondition.
            pd._rfid_reader.set_event_sink.call_args.args[0](
                'card.detected', {'uid': 'AA:BB'})
            pd.subscription.request.assert_called_once_with('printer.emergency_stop')
            core.close()
