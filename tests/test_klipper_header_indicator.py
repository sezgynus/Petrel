"""Header Klipper connection indicator: bounded native rendering and lifecycle."""
import unittest
from unittest.mock import call, patch

from graphite_theme import (
    AXIS_HOMED_COLOR, AXIS_UNHOMED_COLOR, AXIS_UNKNOWN_COLOR, KLIPPER_ERROR_COLOR)
from printer_state import PrinterState
from test_capabilities import display, snapshot
from test_regressions import ui


class KlipperHeaderIndicatorTests(unittest.TestCase):
    @staticmethod
    def make():
        v = display(snapshot())
        v.pd.connection_error = None
        return v

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_first_draw_is_only_four_by_four_and_idle_sends_no_commands(self, clock):
        v = self.make()
        self.assertTrue(v._draw_header_clock())
        v.lcd.draw_rectangle.assert_called_once_with(
            1, AXIS_HOMED_COLOR, 267, 12, 270, 15)
        v.lcd.reset_mock()
        self.assertFalse(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_connecting_disconnected_unknown_and_ready_are_distinct(self, clock):
        v = self.make()
        v._draw_header_clock()
        source = snapshot()
        for state, color in (
                ('connecting', AXIS_UNHOMED_COLOR),
                ('disconnected', KLIPPER_ERROR_COLOR),
                ('unknown', AXIS_UNKNOWN_COLOR),
                ('ready', AXIS_HOMED_COLOR)):
            source['state'] = state
            v.pd.state = PrinterState.from_snapshot(source)
            v.lcd.reset_mock()
            self.assertTrue(v._draw_header_clock())
            self.assertEqual(v.lcd.method_calls, [
                call.draw_rectangle(1, color, 267, 12, 270, 15)])
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
        self.assertEqual(v.lcd.method_calls, [
            call.draw_rectangle(1, KLIPPER_ERROR_COLOR, 267, 12, 270, 15)])

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
            call(1, v.lcd.Color_Bg_Blue, 200, 4, 219, 23),
            call(1, AXIS_UNHOMED_COLOR, 267, 12, 270, 15)])
        self.assertEqual(v.lcd.show_icon.call_count, 1)
        v.lcd.reset_mock()
        self.assertFalse(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_title_clear_repaints_dot_even_if_lifecycle_is_unchanged(self, clock):
        v = self.make()
        v.Clear_Title_Bar()
        v.lcd.reset_mock()
        v.Clear_Title_Bar()
        self.assertIn(call(1, AXIS_HOMED_COLOR, 267, 12, 270, 15),
                      v.lcd.draw_rectangle.call_args_list)


if __name__ == '__main__':
    unittest.main()
