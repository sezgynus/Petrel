"""Event melody validity and bounded named melody playback."""
from threading import Event
import unittest
from unittest.mock import Mock, call, patch

from petrel.features.buzzer.control import Player, Settings
from petrel.features.buzzer.melodies import MELODIES, get_melody


class MelodyTests(unittest.TestCase):
    def test_event_scores_are_distinct_short_valid_and_include_rests(self):
        names = ('PRINT_DONE', 'HEATING_DONE', 'COOLING_DONE', 'ERROR',
                 'FILAMENT_OUT', 'BOOT', 'SHUTDOWN', 'PAUSE', 'RESUME',
                 'LAYER_CHANGE', 'HOMING', 'PROBE_SUCCESS', 'PROBE_FAIL',
                 'WARNING', 'CUSTOM_EVENT')
        scores = [get_melody(name) for name in names]
        self.assertEqual(len(set(scores)), 15)
        for name, score in zip(names, scores):
            with self.subTest(name=name):
                self.assertGreater(sum(duration for _, duration in score), 0)
                self.assertLess(sum(duration for _, duration in score), 1.5)
                self.assertTrue(any(frequency == 0 for frequency, _ in score))
                self.assertTrue(all(0 <= frequency <= 4186 and 0 < duration <= .3
                                    for frequency, duration in score))
        self.assertLess(sum(duration for _, duration in get_melody('LAYER_CHANGE')), .2)
        with self.assertRaises(TypeError):
            MELODIES['BOOT'] = ()

    def test_named_playback_rests_volume_and_no_click_preference_dependency(self):
        pwm, finished = Mock(), Event()
        pwm.tone.side_effect = lambda hz, volume: finished.set() if hz == 988 else None
        with patch('petrel.features.buzzer.control.get_melody', return_value=((784, .001), (0, .001), (988, .001))):
            player = Player(driver_factory=lambda: pwm)
            try:
                self.assertTrue(player.play_melody('RESUME', Settings(volume=30, click=0, encoder=0)))
                self.assertTrue(finished.wait(1))
            finally:
                player.close()
        self.assertEqual(pwm.tone.call_args_list, [call(784,30), call(988,30)])
        self.assertGreaterEqual(pwm.off.call_count, 2)

    def test_named_playback_is_bounded_and_emergency_preempts(self):
        pwm, started, emergency = Mock(), Event(), Event()
        pwm.tone.side_effect = lambda hz, volume: started.set() if hz == 1319 else emergency.set()
        with patch('petrel.features.buzzer.control.get_melody', return_value=((1319, 10),)), \
             patch('petrel.features.buzzer.control.EMERGENCY_PATTERN', ((2200,10),)):
            player = Player(driver_factory=lambda: pwm)
            try:
                self.assertTrue(player.play_melody('PRINT_DONE', Settings()))
                self.assertTrue(started.wait(1))
                for _ in range(20):
                    self.assertFalse(player.play_melody('BOOT', Settings()))
                self.assertTrue(player.play_emergency())
                self.assertTrue(emergency.wait(1))
                self.assertFalse(player.play_melody('BOOT', Settings(), priority=True))
            finally:
                player.close()
        self.assertEqual(pwm.tone.call_args_list, [call(1319,50), call(2200,100)])

    def test_mute_unknown_name_and_closed_player(self):
        pwm = Mock()
        player = Player(driver_factory=lambda: pwm)
        try:
            for settings in (Settings(enabled=False), Settings(volume=0)):
                self.assertFalse(player.play_melody('BOOT', settings))
            self.assertFalse(player.play_melody('OFF', Settings()))
            for name in ('missing', None, []):
                with self.assertRaises(ValueError):
                    player.play_melody(name, Settings())
        finally:
            player.close()
        self.assertFalse(player.play_melody('BOOT', Settings()))
        pwm.tone.assert_not_called()
