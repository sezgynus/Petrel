from unittest import TestCase
from unittest.mock import Mock
from test_capabilities import display, snapshot
from buzzer_melodies import MELODIES


class MelodyTestMenuTests(TestCase):
    def view(self):
        view = display(snapshot())
        view._display_edit = False
        view._rotation_steps = 1
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        return view

    def test_display_entry_and_initial_back_focus(self):
        view = self.view()
        view._draw_list_menu = Mock()
        view.Draw_Display_Menu()
        self.assertEqual(view._draw_list_menu.call_args.args[1][-1][0], 'Melody test')
        view._display_selection = 5 + len(view._buzzer_rows())
        view.HMI_Display_Menu()
        self.assertEqual(view.checkkey, view.MelodyTestMenu)
        self.assertEqual(view._melody_test_selection, 0)
        rows = view._draw_list_menu.call_args.args[1]
        self.assertEqual(len(rows), len(MELODIES) + 2)
        self.assertEqual(rows[0][0], 'Back')

    def test_every_score_reaches_shared_player_and_back_stops(self):
        view = self.view()
        view.checkkey = view.MelodyTestMenu
        view._play_buzzer_melody = Mock()
        view._buzzer_player = Mock()
        for index, name in enumerate(MELODIES, 2):
            view._melody_test_selection = index
            view.HMI_Melody_Test_Menu()
            view._play_buzzer_melody.assert_called_with(name, priority=True)
        view._melody_test_selection = 1
        view.HMI_Melody_Test_Menu()
        view._buzzer_player.cancel.assert_called_once()
        view._melody_test_selection = 0
        view.HMI_Melody_Test_Menu()
        self.assertEqual(view.checkkey, view.DisplayMenu)
        self.assertEqual(view._buzzer_player.cancel.call_count, 2)
        self.assertEqual(view._display_selection, 5 + len(view._buzzer_rows()))

    def test_encoder_bounds_and_scroll(self):
        view = self.view()
        view.checkkey = view.MelodyTestMenu
        view._rotation_steps = 100
        view.get_encoder_state.return_value = view.ENCODER_DIFF_CW
        view.HMI_Melody_Test_Menu()
        self.assertEqual(view._melody_test_selection, len(MELODIES) + 1)
        view.get_encoder_state.return_value = view.ENCODER_DIFF_CCW
        view.HMI_Melody_Test_Menu()
        self.assertEqual(view._melody_test_selection, 0)
