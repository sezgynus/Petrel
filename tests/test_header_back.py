"""Global return navigation: fixed title control and full body viewport."""
import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot


class HeaderBackTests(unittest.TestCase):
    def view(self):
        view = display(snapshot(probe=True))
        view.lcd.DWIN_WIDTH = 272
        return view

    def test_return_is_not_a_body_row_and_first_action_uses_row_zero(self):
        v = self.view()
        painter = Mock()
        entries = [('Back', v.ICON_Back, None, None),
                   ('First action', v.ICON_Info, None, painter)]
        v._draw_list_menu('A long menu title that must fit', entries, 0)
        self.assertEqual(v._list_render['start'], 1)
        painter.assert_called_once_with(0)
        self.assertFalse(any(c.args[-1] == 'Back'
                             for c in v.lcd.draw_text.call_args_list))
        v.lcd.show_icon.assert_any_call(
            v.ICON, v.ICON_Back, 6, 5, background=False, enhanced=True)
        self.assertEqual(v._menu_row(1), 0)
        v.lcd.reset_mock()
        v._draw_list_menu('A long menu title that must fit', entries, 0)
        self.assertEqual(v.lcd.method_calls, [])

    def test_header_focus_and_body_scroll_keep_action_indices(self):
        v = self.view()
        entries = [('Back', v.ICON_Back, None, None)] + [
            ('Action %d' % i, 0, None, None) for i in range(1, 10)]
        v._draw_list_menu('List', entries, 0)
        for selected in (1, 6, 7, 9, 0):
            v.lcd.reset_mock()
            v._draw_list_menu('List', entries, selected)
            self.assertGreaterEqual(v._list_render['start'], 1)
            if selected:
                self.assertGreaterEqual(v._menu_row(selected), 0)
                self.assertLess(v._menu_row(selected), v.TROWS)
            for call in v.lcd.move_area.call_args_list:
                self.assertGreaterEqual(call.args[5], 31)
            self.assertFalse(any(c.args[-1] == 'Back'
                                 for c in v.lcd.draw_text.call_args_list))

    def test_standard_menu_families_never_draw_back_text(self):
        for name in ('Draw_Prepare_Menu', 'Draw_Control_Menu', 'Draw_Move_Menu',
                     'Draw_Display_Menu', 'Draw_Bed_Mesh_Menu',
                     'Draw_Screws_Menu', 'Draw_Case_Light_Menu'):
            with self.subTest(menu=name):
                v = self.view()
                getattr(v, name)()
                self.assertFalse(any(c.args[-1] == 'Back'
                                     for c in v.lcd.draw_text.call_args_list))
                self.assertEqual(v._list_render['start'], 1)
