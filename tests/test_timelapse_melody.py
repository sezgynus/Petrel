from unittest import TestCase
from unittest.mock import Mock

from petrel.moonraker.subscription import MoonrakerSubscription, TIMELAPSE_MACRO


class TimelapseMelodyTests(TestCase):
    def setUp(self):
        self.sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(self.sub.close)
        self.melody = Mock()
        self.sub.set_melody_callback(self.melody)
        self.sub._merge({'print_stats': {'state': 'printing', 'filename': 'part.gcode'}},
                        1, replace=True)
        self.sub._state = 'ready'

    def test_frame_pause_and_resume_are_silent_even_if_flag_clears_with_resume(self):
        self.sub._merge({TIMELAPSE_MACRO: {'is_paused': True}}, 2)
        self.sub._merge({'print_stats': {'state': 'paused'}}, 3)
        self.sub._merge({'print_stats': {'state': 'printing'},
                         TIMELAPSE_MACRO: {'is_paused': False}}, 4)
        self.melody.assert_not_called()
        self.sub._merge({'print_stats': {'state': 'paused'}}, 5)
        self.sub._merge({'print_stats': {'state': 'printing'}}, 6)
        self.assertEqual([call.args[0] for call in self.melody.call_args_list],
                         ['PAUSE', 'RESUME'])

    def test_pause_and_resume_sound_without_timelapse_macro(self):
        self.sub._merge({'print_stats': {'state': 'paused'}}, 2)
        self.sub._merge({'print_stats': {'state': 'printing'}}, 3)
        self.assertEqual([call.args[0] for call in self.melody.call_args_list],
                         ['PAUSE', 'RESUME'])

    def test_error_during_frame_is_audible(self):
        self.sub._merge({'print_stats': {'state': 'paused'},
                         TIMELAPSE_MACRO: {'is_paused': True}}, 2)
        self.sub._merge({'print_stats': {'state': 'error'}}, 3)
        self.melody.assert_called_once_with('ERROR', 0)
