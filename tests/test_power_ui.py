import unittest
from unittest.mock import Mock

from test_capabilities import display, snapshot


class PowerUITests(unittest.TestCase):
    def view(self):
        result = display(snapshot())
        result._power_focus = False
        result._power_origin = None
        result._power_confirm_yes = True
        result.pd.power_off_if_on = Mock()
        return result

    def test_first_item_does_not_focus_removed_power_icon(self):
        result = self.view()
        result.checkkey = result.Prepare
        result.select_prepare.reset()
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CCW)
        self.assertFalse(result._handle_power_navigation())
        self.assertFalse(result._power_focus)

    def test_hold_popup_starts_with_cancel(self):
        result = self.view()
        result.checkkey = result.Control
        result._open_power_hold_popup()
        self.assertEqual(result.checkkey, result.PowerConfirm)
        self.assertFalse(result._power_confirm_yes)
        result.pd.power_off_if_on.assert_not_called()

    def test_external_print_closes_power_dialog_instead_of_restoring_control(self):
        for origin in ('Control', 'MMUMenu'):
            result = self.view()
            result.checkkey = getattr(result, origin)
            result._open_power_hold_popup()
            result.pd.status = 'printing'
            result.Goto_PrintProcess = Mock(
                side_effect=lambda: setattr(result, 'checkkey', result.PrintProcess))
            result._update_ui_state = Mock()
            result._focus_tick_quiet = Mock()
            with self.subTest(origin=origin):
                self.assertTrue(result._power_popup_tick())
                self.assertEqual(result.checkkey, result.PrintProcess)
                self.assertIsNone(result._power_origin)
                result.pd.power_off_if_on.assert_not_called()

    def test_confirmation_yes_powers_off_and_no_restores_origin(self):
        result = self.view()
        result.checkkey = result.PowerConfirm
        result._power_origin = result.MainMenu
        result._power_confirm_yes = True
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result._show_message = Mock()
        result._handle_power_navigation()
        result.pd.power_off_if_on.assert_called_once_with()
        result._show_message.assert_called_once_with('Powering off...')

        result = self.view()
        result.checkkey = result.PowerConfirm
        result._power_origin = result.MainMenu
        result._power_confirm_yes = False
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.Goto_MainMenu = Mock()
        result._handle_power_navigation()
        result.pd.power_off_if_on.assert_not_called()
        result.Goto_MainMenu.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
