"""Original M300 score fidelity and bounded named melody playback."""
from threading import Event
import unittest
from unittest.mock import Mock, call, patch

from buzzer_control import Player, Settings
from buzzer_melodies import MELODIES, get_melody


class MelodyTests(unittest.TestCase):
    def test_original_m300_frequencies_durations_and_rests(self):
        original = {
            'PRINT_DONE': '1319:150 1568:150 1760:150 2093:300 0:150 2093:300',
            'HEATING_DONE': '784:150 988:150 1319:200 1760:200 1568:200 1976:400',
            'COOLING_DONE': '2093:150 1760:150 1319:250 988:300 784:300 523:400',
            'ERROR': '1046:200 784:200 523:200 0:100 523:250 494:300 440:400',
            'FILAMENT_OUT': '1568:150 0:50 1568:150 0:50 880:200 988:250 784:300',
            'BOOT': '880:120 1175:120 1568:120 2093:200 2637:200 3136:250 4186:400',
            'SHUTDOWN': '2093:200 1760:200 1319:200 988:250 784:400 523:400',
            'PAUSE': '1568:150 1175:150 880:300 0:100 880:250 1319:250',
            'RESUME': '784:150 1046:150 1319:200 1760:250 2093:300',
            'LAYER_CHANGE': '2093:100 0:40 2349:120 0:40 2637:150 0:40 3136:180',
            'HOMING': '1046:150 1175:150 1319:150 1568:250 1760:250',
            'PROBE_SUCCESS': '988:150 1175:150 1568:150 2093:250 2637:250',
            'PROBE_FAIL': '2093:120 1976:120 1760:150 1319:250 988:400',
            'WARNING': '1175:150 1175:150 1175:150 0:100 784:250 880:400',
            'CUSTOM_EVENT': '987:150 740:150 987:150 1319:200 1760:300 2093:400',
        }
        for name, notes in original.items():
            with self.subTest(name=name):
                expected = tuple(tuple(map(int, note.split(':'))) for note in notes.split())
                actual = tuple((hz, round(seconds * 1000)) for hz, seconds in get_melody(name))
                self.assertEqual(actual, expected)
        with self.assertRaises(TypeError):
            MELODIES['BOOT'] = ()

    def test_named_playback_rests_volume_and_no_click_preference_dependency(self):
        pwm, finished = Mock(), Event()
        pwm.tone.side_effect = lambda hz, volume: finished.set() if hz == 988 else None
        with patch('buzzer_control.get_melody', return_value=((784, .001), (0, .001), (988, .001))):
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
        with patch('buzzer_control.get_melody', return_value=((1319, 10),)), \
             patch('buzzer_control.EMERGENCY_PATTERN', ((2200,10),)):
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
