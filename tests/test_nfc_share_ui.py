"""NFC URI share UI: one Core-gated component and event-owned popup."""
from concurrent.futures import Future
import unittest
from unittest.mock import Mock

from info_qr import PROJECT_URL, extra_info_rows
from ui_events import InputEvent
from ui_nfc_share import NFCURIShareComponent
from test_capabilities import display, snapshot


class NFCShareUITests(unittest.TestCase):
    def screen(self, supported=True, ready=True):
        view = display(snapshot())
        core = Mock()
        core.get_capabilities.return_value = {'ndef_uri_emulation': supported}
        core.is_ready.return_value = ready
        view._nfc_uri_share = NFCURIShareComponent(core)
        view._closed = False
        view._uart_online = True
        view.checkkey = view.Info
        view._info_scroll = 0
        return view, core

    def test_capability_gates_action_without_per_screen_backend_access(self):
        view, core = self.screen(False)
        component = view._nfc_share_component()
        self.assertFalse(component.visible)
        self.assertNotIn('nfc_share', [kind for kind, _, _ in view._info_items()])
        for supported, ready, expected, changed in (
                (None, True, False, False), (True, False, False, False),
                (True, True, True, True), (False, True, False, True)):
            core.get_capabilities.return_value = {'ndef_uri_emulation': supported}
            core.is_ready.return_value = ready
            self.assertEqual(component.sync(), changed)
            self.assertEqual(component.visible, expected)
            self.assertEqual('nfc_share' in [kind for kind, _, _ in view._info_items()],
                             expected)
        core.share_ndef_uri.assert_not_called()

    def test_core_capability_event_updates_info_layout_without_timer(self):
        view, core = self.screen(False)
        view.Draw_Info_Menu = Mock()
        view.pd.sync_nfc_event = Mock(return_value=False)
        core.get_capabilities.return_value = {'ndef_uri_emulation': True}
        view._process_input_untraced(InputEvent('nfc_capabilities', 0, 0, 0))
        self.assertTrue(view._nfc_share_component().visible)
        view.Draw_Info_Menu.assert_called_once_with()
        view.lcd.update.assert_called_once()
        view.Draw_Info_Menu.reset_mock()
        view.lcd.update.reset_mock()
        view._process_input_untraced(InputEvent('nfc_capabilities', 0, 0, 0))
        view.Draw_Info_Menu.assert_not_called()
        view.lcd.update.assert_not_called()

    def test_info_button_is_directly_below_qr_with_update_still_last(self):
        view, core = self.screen()
        items = view._info_items()
        self.assertEqual(items[-3][0], 'qr')
        self.assertEqual(items[-2], ('nfc_share', 'Share via NFC', PROJECT_URL))
        self.assertEqual(items[-1][0], 'update')
        end = len(items) + extra_info_rows() - 11
        view._info_scroll = end - 1
        view.Draw_Info_Menu()
        share_labels = [c.args for c in view.lcd.draw_text.call_args_list
                        if c.args[-1] == 'Share via NFC']
        self.assertTrue(share_labels)
        self.assertEqual(share_labels[-1][-2], 286)
        self.assertEqual(view._info_scroll, end - 1)

    def test_popup_transfers_repository_uri_and_closes_on_complete_event(self):
        view, core = self.screen()
        pending = Future()
        core.share_ndef_uri.return_value = pending
        items = view._info_items()
        view._info_scroll = len(items) + extra_info_rows() - 12
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.HMI_Info()
        self.assertEqual(view._nfc_share_popup, 'waiting')
        core.share_ndef_uri.assert_called_once_with(PROJECT_URL)
        view.Draw_Info_Menu = Mock()
        view.lcd.reset_mock()
        view._process_input_untraced(InputEvent('nfc_share_done', 0, 0, 0))
        self.assertIsNone(view._nfc_share_popup)
        view.Draw_Info_Menu.assert_called_once_with()
        view.lcd.update.assert_called_once()
        core.cancel_share.assert_not_called()

    def test_failed_share_stays_visible_and_press_cancels(self):
        view, core = self.screen()
        core.share_ndef_uri.return_value = Future()
        self.assertTrue(view._start_nfc_share_popup())
        view._process_input_untraced(InputEvent('nfc_share_failed', 0, 0, 0))
        self.assertEqual(view._nfc_share_popup, 'failed')
        view.Draw_Info_Menu = Mock()
        view._process_input_untraced(InputEvent('press', 0, 0, 0))
        self.assertIsNone(view._nfc_share_popup)
        core.cancel_share.assert_called_once()
        view.Draw_Info_Menu.assert_called_once_with()

    def test_immediate_rejection_is_reported_in_popup(self):
        view, core = self.screen()
        failed = Future()
        failed.set_exception(OSError('Device busy'))
        core.share_ndef_uri.return_value = failed
        self.assertTrue(view._start_nfc_share_popup())
        self.assertEqual(view._nfc_share_popup, 'failed')
        self.assertTrue(view._nfc_share_component().visible)
