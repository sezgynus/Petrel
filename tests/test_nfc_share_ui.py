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

    def test_info_share_reuses_petrel_row_without_changing_layout(self):
        view, core = self.screen()
        items = view._info_items()
        index = next(i for i, item in enumerate(items) if item[0] == 'nfc_share')
        self.assertEqual(items[index][1], 'Petrel')
        self.assertEqual(items[-2][0], 'qr')
        self.assertEqual(items[-1][0], 'update')
        self.assertEqual(items[index + 1][1], 'Klipper')
        view._info_scroll = index - 1
        view.Draw_Info_Menu()
        view.lcd.show_icon.assert_any_call(3, 187, 92, 114,
                                           background=False, enhanced=True)
        self.assertFalse(any(c.args[-1] == 'Share via NFC'
                             for c in view.lcd.draw_text.call_args_list))
        core.is_ready.return_value = False
        view._nfc_share_component().sync()
        hidden = view._info_items()
        self.assertEqual(len(hidden), len(items))
        self.assertEqual(hidden[index][0:2], ('row', 'Petrel'))

    def test_normal_selected_and_hidden_button_follow_capability_event(self):
        view, core = self.screen()
        items = view._info_items()
        index = next(i for i, item in enumerate(items) if item[0] == 'nfc_share')
        view._info_scroll = index - 2
        view.Draw_Info_Menu()
        view.lcd.show_icon.assert_any_call(3, 186, 92, 138,
                                           background=False, enhanced=True)
        view._info_scroll = index - 1
        view.Draw_Info_Menu()
        view.lcd.show_icon.assert_any_call(3, 187, 92, 114,
                                           background=False, enhanced=True)
        core.get_capabilities.return_value = {'ndef_uri_emulation': False}
        view.pd.sync_nfc_event = Mock(return_value=False)
        view.lcd.reset_mock()
        view._process_input_untraced(InputEvent('nfc_capabilities', 0, 0, 0))
        self.assertFalse(any(c.args[1] in (186, 187)
                             for c in view.lcd.show_icon.call_args_list))

    def test_popup_transfers_repository_uri_and_closes_on_complete_event(self):
        view, core = self.screen()
        pending = Future()
        core.share_ndef_uri.return_value = pending
        items = view._info_items()
        view._info_scroll = next(i for i, item in enumerate(items)
                                 if item[0] == 'nfc_share') - 1
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

    def test_native_animation_starts_once_and_stops_on_completion(self):
        view, core = self.screen()
        core.share_ndef_uri.return_value = Future()
        view._start_nfc_share_popup()
        view.lcd.configure_animation.assert_called_once_with(
            2, True, 3, 174, 185, 56, 116, 20)
        view._process_input_untraced(InputEvent('nfc_share_done', 0, 0, 0))
        self.assertIn(((2, False, 3, 174, 185, 56, 116, 20), {}),
                      view.lcd.configure_animation.call_args_list)

    def test_native_animation_stops_on_failure_cancel_and_window_replacement(self):
        for action in ('failure', 'cancel', 'main', 'popup'):
            with self.subTest(action=action):
                view, core = self.screen()
                core.share_ndef_uri.return_value = Future()
                view._start_nfc_share_popup()
                view.lcd.configure_animation.reset_mock()
                if action == 'failure':
                    view._process_input_untraced(InputEvent('nfc_share_failed', 0, 0, 0))
                elif action == 'cancel':
                    view._cancel_nfc_share_popup()
                elif action == 'main':
                    view.Clear_Main_Window()
                else:
                    view.Clear_Popup_Area()
                view.lcd.configure_animation.assert_called_once_with(
                    2, False, 3, 174, 185, 56, 116, 20)
