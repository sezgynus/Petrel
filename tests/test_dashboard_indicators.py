"""Low-cost Graphite dashboard status markers: semantics and dirty rectangles."""
import unittest
from unittest.mock import call, patch

from graphite_theme import AXIS_HOMED_COLOR, AXIS_UNHOMED_COLOR, AXIS_UNKNOWN_COLOR
from printer_state import PrinterState
from test_capabilities import display, snapshot
from test_regressions import ui


class DashboardIndicatorTests(unittest.TestCase):
    def make(self, data=None):
        view = display(data or snapshot())
        view.lcd.DWIN_WIDTH = 272
        view.lcd.DWIN_HEIGHT = 480
        view.lcd.Line_Color = 0x39C8
        view.checkkey = view.MainMenu
        return view

    @staticmethod
    def change_state(view, data):
        view.pd.state = PrinterState.from_snapshot(data)

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_initial_heater_and_extrusion_markers_are_bounded(self, clock):
        view = self.make()
        view.Draw_Status_Area(False)
        markers = [c.args for c in view.lcd.draw_rectangle.call_args_list
                   if c.args[3] in (402, 436)]
        self.assertEqual(markers, [
            (1, AXIS_UNHOMED_COLOR, 7, 402, 18, 404),
            (1, AXIS_HOMED_COLOR, 20, 402, 23, 404),
            (1, AXIS_UNHOMED_COLOR, 7, 436, 20, 438),
        ])
        view.lcd.reset_mock()
        view.Draw_Status_Area(True)
        self.assertEqual(view.lcd.method_calls, [])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_hotend_tolerance_hysteresis_repaints_only_one_bar(self, clock):
        data = snapshot()
        view = self.make(data)
        view.Draw_Status_Area(False)
        for temperature, expected in ((203.0, AXIS_HOMED_COLOR),
                                      (202.2, None),
                                      (201.9, AXIS_UNHOMED_COLOR)):
            data['status']['extruder']['temperature'] = temperature
            self.change_state(view, data)
            view.lcd.reset_mock()
            view.Draw_Status_Area(True)
            self.assertEqual(view.lcd.method_calls, [] if expected is None else
                             [call.draw_rectangle(1, expected, 7, 402, 18, 404)])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_heat_off_and_bed_ready_do_not_affect_other_markers(self, clock):
        data = snapshot()
        view = self.make(data)
        view.Draw_Status_Area(False)
        data['status']['extruder'].update(target=0, temperature=30)
        data['status']['heater_bed'].update(target=60, temperature=59)
        self.change_state(view, data)
        view.lcd.reset_mock()
        view.Draw_Status_Area(True)
        self.assertEqual(view.lcd.method_calls, [
            call.draw_rectangle(1, view.lcd.Line_Color, 7, 402, 18, 404),
            call.draw_rectangle(1, AXIS_HOMED_COLOR, 7, 436, 20, 438),
        ])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_can_extrude_is_independent_of_heater_target(self, clock):
        data = snapshot()
        view = self.make(data)
        view.Draw_Status_Area(False)
        for value, expected in ((False, AXIS_UNHOMED_COLOR),
                                (None, AXIS_UNKNOWN_COLOR),
                                (True, AXIS_HOMED_COLOR)):
            if value is None:
                data['status']['extruder'].pop('can_extrude', None)
            else:
                data['status']['extruder']['can_extrude'] = value
            self.change_state(view, data)
            view.lcd.reset_mock()
            view.Draw_Status_Area(True)
            self.assertEqual(view.lcd.method_calls,
                             [call.draw_rectangle(1, expected, 20, 402, 23, 404)])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_speed_and_flow_overrides_ignore_two_second_telemetry_phase(self, clock):
        view = self.make()
        view.Draw_Status_Area(False)
        view.lcd.reset_mock()
        view.pd.feedrate_percentage = 120.0
        view.pd.flow_percentage = 95.0
        view.Draw_Status_Area(True)
        self.assertEqual(view.lcd.method_calls, [
            call.draw_rectangle(1, AXIS_UNHOMED_COLOR, 105, 402, 118, 404),
            call.draw_rectangle(1, AXIS_UNHOMED_COLOR, 105, 436, 118, 438),
        ])
        view.lcd.reset_mock()
        with patch.object(ui.time, 'monotonic', return_value=6):
            view.Draw_Status_Area(True)
        # Alternating shorter values may clear text, but never touch markers.
        marker_coords = {(105, 402, 118, 404), (105, 436, 118, 438)}
        self.assertEqual([
            c.args for c in view.lcd.draw_rectangle.call_args_list
            if c.args[-4:] in marker_coords], [])
        view.lcd.reset_mock()
        view.pd.feedrate_percentage = 100
        view.pd.flow_percentage = 100
        view.Draw_Status_Area(True)
        self.assertEqual([
            c.args for c in view.lcd.draw_rectangle.call_args_list
            if c.args[-4:] in marker_coords], [
            (1, 0x18C4, 105, 402, 118, 404),
            (1, 0x18C4, 105, 436, 118, 438),
        ])
        view.lcd.reset_mock()
        view.Draw_Status_Area(True)
        self.assertEqual(view.lcd.method_calls, [])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_mesh_indicator_reads_active_matrix_not_saved_profiles(self, clock):
        data = snapshot(probe=True)
        data['status']['bed_mesh'] = {
            'profile_name': 'saved', 'mesh_matrix': [], 'profiles': {'saved': {}}}
        view = self.make(data)
        view.Draw_Status_Area(False)
        self.assertFalse(any(c.args[-3:] == (436, 211, 439)
                             for c in view.lcd.draw_rectangle.call_args_list))
        data['status']['bed_mesh'].update(profile_name='', mesh_matrix=[[0, .01]])
        self.change_state(view, data)
        view.lcd.reset_mock()
        view.Draw_Status_Area(True)
        self.assertEqual(view.lcd.method_calls, [
            call.draw_rectangle(1, AXIS_HOMED_COLOR, 208, 436, 211, 439)])
        data['status']['bed_mesh']['mesh_matrix'] = []
        self.change_state(view, data)
        view.lcd.reset_mock()
        view.Draw_Status_Area(True)
        self.assertEqual(view.lcd.method_calls, [
            call.draw_rectangle(1, 0x18C4, 208, 436, 211, 439)])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_disconnection_clears_active_mesh_and_overrides(self, clock):
        data = snapshot(probe=True)
        data['status']['bed_mesh'] = {'profile_name': '', 'mesh_matrix': [[0]]}
        view = self.make(data)
        view.pd.flow_percentage = 112
        view.Draw_Status_Area(False)
        data['state'] = 'connecting'
        self.change_state(view, data)
        view.lcd.reset_mock()
        view.Draw_Status_Area(True)
        rects = [c.args for c in view.lcd.draw_rectangle.call_args_list]
        self.assertIn((1, 0x18C4, 105, 436, 118, 438), rects)
        self.assertIn((1, 0x18C4, 208, 436, 211, 439), rects)
        self.assertIn((1, AXIS_UNKNOWN_COLOR, 7, 402, 18, 404), rects)
        self.assertIn((1, AXIS_UNKNOWN_COLOR, 20, 402, 23, 404), rects)

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_dashboard_reentry_redraws_cached_indicators(self, clock):
        view = self.make()
        view.Draw_Status_Area(False)
        view.lcd.reset_mock()
        view.Draw_Status_Area(False)
        rects = [c.args for c in view.lcd.draw_rectangle.call_args_list]
        self.assertIn((1, AXIS_UNHOMED_COLOR, 7, 402, 18, 404), rects)
        self.assertIn((1, AXIS_HOMED_COLOR, 20, 402, 23, 404), rects)
        self.assertIn((1, AXIS_UNHOMED_COLOR, 7, 436, 20, 438), rects)


if __name__ == '__main__':
    unittest.main()
