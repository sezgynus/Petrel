import unittest
from unittest.mock import patch
from test_capabilities import display, snapshot
from test_regressions import ui
from test_mmu_control import mmu_snapshot
from petrel.printer.state import PrinterState
from petrel.ui.theme import AXIS_HOMED_COLOR, AXIS_UNHOMED_COLOR, AXIS_UNKNOWN_COLOR
from petrel.artwork.resources import ICON_WIFI_POOR, ICON_WIFI_MEDIUM, ICON_WIFI_STRONG, ICON_PROGRESS_FILL
from unittest.mock import call


class IncrementalDashboardTests(unittest.TestCase):
    def make(self, data=None):
        v = display(data or snapshot())
        v.lcd.DWIN_WIDTH = 272
        v.lcd.DWIN_HEIGHT = 480
        v.lcd.Line_Color = 0x3A6A
        v.checkkey = v.MainMenu
        return v

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_unchanged_status_sends_no_drawing(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_only_changed_temperature_is_drawn(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        v.pd.thermalManager['temp_hotend'][0]['celsius'] = 201
        v.Draw_Status_Area(True)
        self.assertEqual(len(v.lcd.method_calls), 1)
        self.assertEqual(v.lcd.draw_text.call_args.args[-3:], (28,380,'201/205'))
        v.lcd.draw_rectangle.assert_not_called()

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_sub_display_precision_does_not_redraw(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        v.pd.thermalManager['temp_hotend'][0]['celsius'] = 200.1
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_shorter_text_clears_trailing_cells_in_one_opaque_packet(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        old = v._status_render[('draw_text',126,380)][-1]
        v.lcd.reset_mock()
        v.pd.live_velocity = 1
        v.Draw_Status_Area(True)
        v.lcd.draw_rectangle.assert_not_called()
        v.lcd.show_icon.assert_not_called()
        new = v.lcd.draw_text.call_args.args
        self.assertEqual((new[1],new[-3:-1]),(True,(126,380)))
        self.assertEqual(new[-1],('1mm/s').ljust(len(old)))
        self.assertEqual(v._status_render[('draw_text',126,380)][-1],'1mm/s')

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_homing_bars_are_14x3_under_each_axis_and_cached(self, clock):
        data = snapshot()
        data['status']['toolhead']['homed_axes'] = 'xz'
        v = self.make(data)
        v.Draw_Status_Area(False)
        bars = [call.args for call in v.lcd.draw_rectangle.call_args_list
                if call.args[-2:] == (118, 472) or
                   call.args[-2:] == (20, 472) or
                   call.args[-2:] == (216, 472)]
        self.assertEqual(bars, [
            (1, AXIS_HOMED_COLOR, 7, 470, 20, 472),
            (1, AXIS_UNHOMED_COLOR, 105, 470, 118, 472),
            (1, AXIS_HOMED_COLOR, 203, 470, 216, 472),
        ])
        v.lcd.reset_mock()
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_homing_change_only_repaints_the_changed_axis(self, clock):
        data = snapshot()
        v = self.make(data)
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        data['status']['toolhead']['homed_axes'] = 'xz'
        v.pd.state = PrinterState.from_snapshot(data)
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [
            unittest.mock.call.draw_rectangle(1, AXIS_UNHOMED_COLOR, 105, 470, 118, 472)])
        v.lcd.reset_mock()
        data['status']['toolhead']['homed_axes'] = 'xyz'
        v.pd.state = PrinterState.from_snapshot(data)
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [
            unittest.mock.call.draw_rectangle(1, AXIS_HOMED_COLOR, 105, 470, 118, 472)])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_disconnected_or_missing_homing_evidence_is_grey_not_homed(self, clock):
        data = snapshot()
        v = self.make(data)
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        data['state'] = 'connecting'
        v.pd.state = PrinterState.from_snapshot(data)
        v.Draw_Status_Area(True)
        self.assertEqual([
            c for c in v.lcd.draw_rectangle.call_args_list if c.args[-1] == 472], [
            unittest.mock.call(1, AXIS_UNKNOWN_COLOR, x, 470, x + 13, 472)
            for x in (7, 105, 203)])
        v.lcd.reset_mock()
        data['state'] = 'ready'
        data['status']['toolhead'].pop('homed_axes')
        v.pd.state = PrinterState.from_snapshot(data)
        v.Draw_Status_Area(True)
        # Non-homing indicators may legitimately restore their known states.
        self.assertEqual([
            c for c in v.lcd.draw_rectangle.call_args_list if c.args[-1] == 472], [])
        v.lcd.reset_mock()
        data['status']['toolhead']['homed_axes'] = ''
        v.pd.state = PrinterState.from_snapshot(data)
        v.Draw_Status_Area(True)
        self.assertEqual([
            c for c in v.lcd.draw_rectangle.call_args_list if c.args[-1] == 472], [
            unittest.mock.call(1, AXIS_UNHOMED_COLOR, x, 470, x + 13, 472)
            for x in (7, 105, 203)])
        v.lcd.reset_mock()
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_wifi_header_uses_native_transparent_icons_only_when_band_changes(self, clock):
        v = self.make()
        v.pd.system_info.update(wifi_ssid='Workshop', wifi_rssi=-58)
        self.assertTrue(v._draw_header_clock())
        v.lcd.show_icon.assert_any_call(
            v.ICON, ICON_WIFI_STRONG, 193, 4, background=False, enhanced=True)
        v.lcd.show_icon.assert_any_call(
            v.ICON, ICON_PROGRESS_FILL, 259, 10, background=False, enhanced=True)
        self.assertEqual(v.lcd.show_icon.call_count, 2)
        v.lcd.reset_mock()
        self.assertFalse(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [])
        for rssi, expected in ((-65, ICON_WIFI_MEDIUM), (-71, ICON_WIFI_POOR),
                               (-60, ICON_WIFI_STRONG)):
            v.pd.system_info['wifi_rssi'] = rssi
            self.assertTrue(v._draw_header_clock())
            self.assertEqual(v.lcd.method_calls, [
                call.draw_rectangle(1, v.lcd.Color_Bg_Blue, 193, 4, 212, 23),
                call.show_icon(v.ICON, expected, 193, 4, background=False, enhanced=True)])
            v.lcd.reset_mock()
        v.pd.system_info['wifi_rssi'] = None
        self.assertTrue(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [
            call.draw_rectangle(1, v.lcd.Color_Bg_Blue, 193, 4, 212, 23)])
        v.lcd.reset_mock()
        self.assertFalse(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_wifi_header_repaints_after_title_clear_and_ignores_ethernet(self, clock):
        v = self.make()
        v.pd.system_info.update(wifi_ssid='Workshop', wifi_rssi=-60)
        v.Clear_Title_Bar()
        self.assertIn((ICON_WIFI_STRONG, 193, 4),
                      [c.args[1:] for c in v.lcd.show_icon.call_args_list])
        v.lcd.reset_mock()
        v.Clear_Title_Bar()
        self.assertIn((ICON_WIFI_STRONG, 193, 4),
                      [c.args[1:] for c in v.lcd.show_icon.call_args_list])
        v.lcd.reset_mock()
        v.pd.system_info.update(network='Online', wifi_ssid='Disconnected', wifi_rssi=None)
        self.assertTrue(v._draw_header_clock())
        self.assertEqual(v.lcd.method_calls, [
            call.draw_rectangle(1, v.lcd.Color_Bg_Blue, 193, 4, 212, 23)])

    def test_unchanged_mmu_sends_no_drawing(self):
        v = self.make(mmu_snapshot())
        v.Draw_MMU_Status()
        v.lcd.reset_mock()
        v.Draw_MMU_Status()
        self.assertEqual(v.lcd.method_calls, [])

    def test_one_percentage_updates_only_its_text_area(self):
        v = self.make(mmu_snapshot())
        mmu = dict(v.pd.mmu)
        mmu['remaining_percent'] = [100, 100, 100, 100]
        with patch.object(v.pd, 'mmu', mmu):
            v.Draw_MMU_Status()
            v.lcd.reset_mock()
            mmu['remaining_percent'][1] = 99
            v.Draw_MMU_Status()
        self.assertEqual(len(v.lcd.method_calls), 2)
        v.lcd.show_icon.assert_not_called()
        self.assertEqual(v.lcd.draw_text.call_args.args[-1], '99%')
        v.lcd.draw_line.assert_not_called()

    def test_same_page_selection_draws_only_two_tiles(self):
        v = self.make()
        v._draw_home_page()
        v.lcd.reset_mock()
        v.select_page.set(1)
        v._draw_home_page(previous=0)
        self.assertEqual(v.lcd.show_icon.call_count, 2)
        self.assertEqual([c.args[-4:] for c in v.lcd.draw_rectangle.call_args_list
                          if c.args[0] == 1], [(17, 130, 126, 229), (145, 130, 254, 229)])

    def test_mmu_is_redrawn_after_leaving_and_returning(self):
        v = self.make(mmu_snapshot())
        v.Goto_MainMenu()
        v.lcd.reset_mock()
        v.Clear_Main_Window()
        v.Draw_MMU_Status()
        self.assertGreaterEqual(v.lcd.show_icon.call_count, 4)
