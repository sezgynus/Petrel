from concurrent.futures import Future
from unittest import TestCase
from unittest.mock import Mock
from pathlib import Path
from PIL import Image, JpegImagePlugin
from test_capabilities import display, snapshot
from petrel.artwork.resources import ICON_LIBRARY_ID, ICON_NFC_CARD_FIRST, ICON_NFC_CARD_LAST


class CardScanPopupTests(TestCase):
    def screen(self):
        view = display(snapshot()); view.checkkey = view.RFIDMenu
        view._uart_online = True; view._rfid_mode = 'emg'; view._rfid_selection = 1
        view._queue_nfc_ui_event = Mock()
        core = Mock(); pending = Future()
        core.global_action_uid.return_value = '01:02'
        core.begin_assignment.return_value = pending
        view.pd.get_nfc_core = Mock(return_value=core)
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.HMI_RFID()
        return view, core, pending

    def test_replace_starts_twelve_native_frames_once_then_requires_save(self):
        view, core, pending = self.screen()
        core.begin_assignment.assert_called_once_with(action='emergency_stop')
        view.lcd.configure_animation.assert_called_once_with(
            3, True, ICON_LIBRARY_ID, 42, 53, 56, 116, 20)
        view.Draw_RFID_Menu(full=False)
        view.get_encoder_state.return_value = view.ENCODER_DIFF_CW
        view.HMI_RFID()
        self.assertEqual(view.lcd.configure_animation.call_count, 1)
        pending.set_result({'uid': 'AA:BB'})
        view._rfid_assignment_event()
        self.assertEqual(view._rfid_mode, 'confirm')
        self.assertEqual(view._rfid_selection, 0)
        core.assign_global_action.assert_not_called()
        view.lcd.configure_animation.assert_any_call(
            3, False, ICON_LIBRARY_ID, 42, 53, 56, 116, 20)

    def test_cancel_reader_failure_and_window_replacement_stop_card_animation(self):
        for action in ('cancel', 'failure', 'window'):
            view, core, pending = self.screen()
            if action == 'cancel':
                view.HMI_RFID(); self.assertTrue(pending.cancelled())
            elif action == 'failure':
                pending.set_exception(OSError('reader lost')); view._rfid_assignment_event()
            else:
                view.Clear_Popup_Area(); self.assertFalse(pending.done())
            self.assertIsNone(view._spool_scan_lcd)
            core.assign_global_action.assert_not_called()
            view.lcd.configure_animation.assert_any_call(
                3, False, ICON_LIBRARY_ID, 42, 53, 56, 116, 20)

    def test_card_frames_are_twelve_opaque_baseline_420_images(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(ICON_NFC_CARD_LAST - ICON_NFC_CARD_FIRST + 1, 12)
        for index in range(ICON_NFC_CARD_FIRST, ICON_NFC_CARD_LAST + 1):
            with Image.open(root / f'assets/icons/{index:03d}.jpg') as image:
                self.assertEqual(image.size, (160, 160))
                self.assertEqual(JpegImagePlugin.get_sampling(image), 2)
                self.assertFalse(image.info.get('progressive'))

