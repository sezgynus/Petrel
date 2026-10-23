from concurrent.futures import Future
from unittest import TestCase
from unittest.mock import Mock
from test_capabilities import display, snapshot
from spoolman_tags import Spool
from lcd_resources import ICON_LIBRARY_ID, ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST


class SpoolScanPopupTests(TestCase):
    def screen(self):
        view = display(snapshot())
        view.checkkey = view.RFIDMenu
        view._uart_online = True
        view._spool_selected = Spool(7, 'Example', 'Red', 'PLA', ('FF0022',))
        view._rfid_mode = 'spool_detail'
        view._spool_selection = 1
        view._queue_nfc_ui_event = Mock()
        core = Mock(); pending = Future()
        core.begin_assignment.return_value = pending
        view.pd.get_nfc_core = Mock(return_value=core)
        view.pd.nfc_assign_spool = Mock()
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.HMI_RFID()
        core.begin_assignment.assert_called_once_with()
        return view, pending

    def test_native_scan_starts_once_and_read_returns_to_explicit_confirmation(self):
        view, pending = self.screen()
        view.lcd.configure_animation.assert_called_once_with(
            3, True, ICON_LIBRARY_ID, ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST, 56, 116, 20)
        view.Draw_RFID_Menu(full=False)
        view.get_encoder_state.return_value = view.ENCODER_DIFF_CW
        view.HMI_RFID()
        self.assertEqual(view.lcd.configure_animation.call_count, 1)
        pending.set_result({'uid': 'AA:BB'})
        view._rfid_assignment_event()
        view.lcd.configure_animation.assert_any_call(
            3, False, ICON_LIBRARY_ID, ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST, 56, 116, 20)
        self.assertEqual(view._rfid_mode, 'spool_confirm')
        self.assertEqual(view._spool_selection, 0)
        view.pd.nfc_assign_spool.assert_not_called()

    def test_click_cancels_without_saving_and_reader_error_stops_animation(self):
        for failed in (False, True):
            view, pending = self.screen()
            if failed:
                pending.set_exception(OSError('reader lost'))
                view._rfid_assignment_event()
            else:
                view.HMI_RFID()
                self.assertTrue(pending.cancelled())
            self.assertEqual(view._rfid_mode, 'spool_detail')
            self.assertIsNone(view._spool_scan_lcd)
            view.lcd.configure_animation.assert_any_call(
                3, False, ICON_LIBRARY_ID, ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST, 56, 116, 20)
            view.pd.nfc_assign_spool.assert_not_called()

    def test_power_overlay_stops_animation_without_losing_capture(self):
        view, pending = self.screen()
        view.Clear_Popup_Area()
        self.assertIsNone(view._spool_scan_lcd)
        self.assertFalse(pending.done())
        view.checkkey = view.PowerConfirm
        view._power_origin = view.RFIDMenu
        pending.set_result({'uid': 'CC:DD'})
        view._rfid_assignment_event()
        self.assertEqual(view._rfid_mode, 'spool_confirm')
        view.pd.nfc_assign_spool.assert_not_called()

    def test_real_navigation_cancels_capture_before_repainting(self):
        view, pending = self.screen()
        view.checkkey = view.MainMenu
        view._rfid_assignment_event()
        self.assertTrue(pending.cancelled())
        self.assertIsNone(view._spool_scan_lcd)
        view.pd.nfc_assign_spool.assert_not_called()
