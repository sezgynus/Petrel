import unittest
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from petrel.features.display_settings.network import NetworkSettings
from petrel.features.display_settings.view import DisplaySettingsViewMixin
from petrel.features.notifications.announcements import ProjectAnnouncements, parse_feed


class NetworkSettingsTest(unittest.TestCase):
    def test_defaults_and_menu_toggles_are_independent_and_persistent(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.json'
            self.assertEqual(NetworkSettings.load(path), NetworkSettings())

            class Display(DisplaySettingsViewMixin):
                ENCODER_DIFF_CW, ENCODER_DIFF_CCW, ENCODER_DIFF_ENTER = range(3)

            display = Display()
            display._display_network = NetworkSettings.load(path)
            display._buzzer_rows = Mock(return_value=(None,) * 4)
            display._buzzer_display_input = Mock(return_value=False)
            display.get_encoder_state = Mock(return_value=display.ENCODER_DIFF_ENTER)
            display.Draw_Display_Menu = Mock()
            display.lcd = Mock()
            with patch('petrel.features.display_settings.network.preferences_path', return_value=path):
                display._display_selection = 10
                display.HMI_Display_Menu()
                self.assertEqual(NetworkSettings.load(path), NetworkSettings(False, True))
                display._display_selection = 11
                display.HMI_Display_Menu()
                self.assertEqual(NetworkSettings.load(path), NetworkSettings(False, False))

    def test_disabled_announcements_do_not_fetch_or_use_in_flight_results(self):
        store = Mock()
        poller = ProjectAnnouncements(store)
        poller._worker = Mock()
        pending = Future()
        pending.set_running_or_notify_cancel()
        poller._worker.submit.return_value = pending
        poller.tick(enabled=False)
        poller._worker.submit.assert_not_called()
        poller.tick()
        poller.tick(enabled=False)
        pending.set_result(parse_feed(b'{"version":1,"announcements":[]}'))
        poller._worker.submit.return_value = Future()
        poller.tick()
        self.assertEqual(poller._worker.submit.call_count, 2)
        store.sync_announcements.assert_not_called()
