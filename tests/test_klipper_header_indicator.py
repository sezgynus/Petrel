"""Header Klipper indicator shares the managed round progress-bar caps."""
import unittest
from unittest.mock import call, patch

from petrel.artwork.resources import (
    ICON_LIBRARY_ID, ICON_PROGRESS_FILL, ICON_PROGRESS_TRACK, ICON_WIFI_STRONG)
from petrel.printer.state import PrinterState
from test_capabilities import display, snapshot
from test_regressions import ui


class KlipperHeaderIndicatorTests(unittest.TestCase):
    @staticmethod
    def make():
        v = display(snapshot())
        v.pd.connection_error = None
        return v

    @staticmethod
    def cap(v, icon):
        v.lcd.draw_rectangle.assert_any_call(
            1, v.lcd.Color_Bg_Blue, 259, 10, 266, 17)
        v.lcd.show_icon.assert_any_call(
            ICON_LIBRARY_ID, icon, 259, 10, background=False, enhanced=True)

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_first_draw_uses_eight_pixel_fill_and_idle_sends_no_commands(self, clock):
        v = self.make()
        self.assertTrue(v._draw_header_clock())
        self.cap(v, ICON_PROGRESS_FILL)
        self.assertEqual(v.lcd.draw_rectangle.call_count, 1)
        self.assertEqual(v.lcd.show_icon.call_count, 1)
        v.lcd.reset_mock()
        self.assertFalse(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_every_non_ready_state_uses_progress_track_and_ready_uses_fill(self, clock):
        v = self.make()
        v._draw_header_clock()
        source = snapshot()
        for state, expected in (
                ('connecting', ICON_PROGRESS_TRACK),
                ('disconnected', ICON_PROGRESS_TRACK),
                ('unknown', ICON_PROGRESS_TRACK),
                ('ready', ICON_PROGRESS_FILL)):
            source['state'] = state
            v.pd.state = PrinterState.from_snapshot(source)
            v.lcd.reset_mock()
            self.assertTrue(v._draw_header_clock())
            self.cap(v, expected)
            self.assertEqual(v.lcd.draw_rectangle.call_count, 1)
            self.assertEqual(v.lcd.show_icon.call_count, 1)
            v.lcd.reset_mock()
            self.assertFalse(v._draw_header_clock())
            self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_subscription_error_takes_precedence_over_stale_ready_status(self, clock):
        v = self.make()
        v._draw_header_clock()
        v.pd.connection_error = 'Klipper shutdown'
        v.lcd.reset_mock()
        self.assertTrue(v._draw_header_clock())
        self.cap(v, ICON_PROGRESS_TRACK)

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_wifi_and_klipper_update_in_same_frame_without_short_circuit(self, clock):
        v = self.make()
        v._draw_header_clock()
        state = snapshot()
        state['state'] = 'connecting'
        v.pd.state = PrinterState.from_snapshot(state)
        v.pd.system_info.update(wifi_ssid='Workshop', wifi_rssi=-59)
        v.lcd.reset_mock()
        self.assertTrue(v._draw_header_clock())
        self.assertEqual(v.lcd.draw_rectangle.call_args_list, [
            call(1, v.lcd.Color_Bg_Blue, 193, 4, 212, 23),
            call(1, v.lcd.Color_Bg_Blue, 259, 10, 266, 17)])
        v.lcd.show_icon.assert_any_call(
            ICON_LIBRARY_ID, ICON_WIFI_STRONG, 193, 4,
            background=False, enhanced=True)
        self.cap(v, ICON_PROGRESS_TRACK)
        self.assertEqual(v.lcd.show_icon.call_count, 2)
        v.lcd.reset_mock()
        self.assertFalse(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_header_cluster_centers_cap_in_right_gap_and_vertically_with_clock(self, clock):
        v = self.make()
        v.pd.system_info.update(wifi_ssid='Workshop', wifi_rssi=-58)
        v.Draw_Title('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        v.lcd.draw_text.assert_any_call(
            False, False, v.lcd.font8x16, v.lcd.Color_White,
            v.lcd.Color_Bg_Blue, 14, 6, 'ABCDEFGHIJKLMNOPQRS...')
        v.lcd.show_icon.assert_any_call(
            ICON_LIBRARY_ID, ICON_WIFI_STRONG, 193, 4,
            background=False, enhanced=True)
        v.lcd.draw_text.assert_any_call(
            False, True, v.lcd.font8x16, v.lcd.Color_White,
            v.lcd.Color_Bg_Blue, 214, 6, '12:34')
        self.cap(v, ICON_PROGRESS_FILL)
        # Title ends at 189; Wi-Fi 193..212; clock 214..253;
        # indicator 259..266: precisely 5px on either side of the cap.
        self.assertEqual(259 - (214 + 5 * 8), 5)
        self.assertEqual(272 - (259 + 8), 5)
        # Clock glyphs are 16px high at y=6; cap is 8px at y=10.
        self.assertEqual(6 + 16 / 2, 10 + 8 / 2)

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_title_clear_repaints_cap_even_if_lifecycle_is_unchanged(self, clock):
        v = self.make()
        v.Clear_Title_Bar()
        v.lcd.reset_mock()
        v.Clear_Title_Bar()
        self.cap(v, ICON_PROGRESS_FILL)

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_header_never_uses_hardcoded_progress_or_klipper_status_colors(self, clock):
        v = self.make()
        v._draw_header_clock()
        for record in v.lcd.draw_rectangle.call_args_list:
            self.assertEqual(record.args[1], v.lcd.Color_Bg_Blue)
        # Actual status color comes only from reusable 94/95 JPEG assets.
        self.assertEqual({call.args[1] for call in v.lcd.show_icon.call_args_list},
                         {ICON_PROGRESS_FILL})


if __name__ == '__main__':
    unittest.main()
