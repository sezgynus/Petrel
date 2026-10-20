"""Native packet contracts for stable menu numeric columns and editor updates."""
import unittest

from PIL import ImageChops

from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer
from test_capabilities import display, snapshot
from test_t5uic1_driver import driver


class MenuValueAlignmentTests(unittest.TestCase):
    def screen(self):
        view = display(snapshot())
        view.lcd = driver()
        return view

    @staticmethod
    def texts(view):
        return [frame for frame in view.lcd.serial.frames if frame[1] == 0x11]

    def test_all_menu_numeric_widths_end_at_historical_240_boundary(self):
        view = self.screen()
        self.assertEqual(view.MENU_VALUE_RIGHT, 240)
        self.assertEqual(view.lcd.FONT_SIZES[view.lcd.font8x16], (8, 16))
        for cells, expected_x in ((3, 216), (7, 184), (9, 168)):
            for value in ('0', '99', '-1.25', '1234567890'):
                with self.subTest(cells=cells, value=value):
                    view.lcd.serial.frames.clear()
                    view._draw_menu_value(value, 102, view.lcd.Color_Bg_Black, cells)
                    frames = view.lcd.serial.frames
                    self.assertEqual(len(frames), 1)
                    self.assertEqual(frames[0][1], 0x11)
                    self.assertEqual(frames[0][2] & 0xC0, 0x40,
                                     'Must use fixed-width opaque text mode')
                    self.assertEqual(int.from_bytes(frames[0][7:9], 'big'), expected_x)
                    self.assertEqual(int.from_bytes(frames[0][9:11], 'big'), 102)
                    text = frames[0][11:-4].decode('ascii')
                    expected = value.rjust(cells) if len(value) <= cells else '#' * cells
                    self.assertEqual(text, expected)
                    self.assertEqual(expected_x + len(text) * 8, 240)

    def test_temperature_rows_and_editors_share_one_right_boundary(self):
        view = self.screen()
        view.Draw_Temperature_Menu()
        text_frames = self.texts(view)
        for label, expected_x in (('205', 184), ('60', 184), ('50', 216)):
            with self.subTest(label=label):
                matches = [frame for frame in text_frames
                           if frame[11:-4].strip() == label.encode('ascii')]
                self.assertEqual(len(matches), 1)
                frame = matches[0]
                self.assertEqual(int.from_bytes(frame[7:9], 'big'), expected_x)
                self.assertEqual(expected_x + 8 * len(frame[11:-4]), 240)
        for key, index, x in (('TEMP', 1, 184), ('BED', 2, 184),
                              ('FAN', 3, 216)):
            with self.subTest(editor=key):
                view.lcd.serial.frames.clear()
                view._open_thermal_editor(key, index)
                frame = self.texts(view)[-1]
                self.assertEqual(int.from_bytes(frame[7:9], 'big'), x)
                self.assertEqual(x + 8 * len(frame[11:-4]), 240)

    def test_temperature_shortening_overwrites_whole_field_in_one_packet(self):
        view = self.screen()
        for old, new in ((250.5, 0), (100, 9), (9, 250.5)):
            with self.subTest(old=old, new=new):
                view.lcd.serial.frames.clear()
                view._draw_thermal_target(old, 102, view.lcd.Color_Bg_Black)
                view._draw_thermal_target(new, 102, view.lcd.Color_Bg_Black)
                frames = view.lcd.serial.frames
                self.assertEqual([f[1] for f in frames], [0x11, 0x11])
                self.assertEqual([int.from_bytes(f[7:9], 'big') for f in frames],
                                 [184, 184])
                self.assertTrue(all(len(f[11:-4]) == 7 and f[2] & 0x40 for f in frames))
                self.assertEqual(frames[-1][11:-4].strip().decode('ascii'), str(new).removesuffix('.0'))

    def test_motion_and_all_move_axes_use_shared_value_columns(self):
        view = self.screen()
        view.checkkey = view.Motion
        view.Draw_Motion_Menu()
        motion = [frame for frame in self.texts(view)
                  if int.from_bytes(frame[7:9], 'big') == 168]
        self.assertEqual(len(motion), len(view.pd.motion_settings()))
        self.assertTrue(all(len(frame[11:-4]) == 9 for frame in motion))
        view.lcd.serial.frames.clear()
        view.Draw_Move_Menu()
        moves = [frame for frame in self.texts(view)
                 if int.from_bytes(frame[7:9], 'big') == 184]
        self.assertEqual(len(moves), 4)
        self.assertTrue(all(len(frame[11:-4]) == 7 for frame in moves))
        for index in range(4):
            view.lcd.serial.frames.clear()
            view._draw_axis_value(index, (index + 1) * view.MINUNITMULT,
                                  102, view.lcd.Select_Color)
            frame = self.texts(view)[-1]
            self.assertEqual(int.from_bytes(frame[7:9], 'big'), 184)
            self.assertEqual(len(frame[11:-4]), 7)

    def test_menus_do_not_steal_dashboard_anchoring(self):
        view = self.screen()
        view._draw_menu_value('100', 102, view.lcd.Color_Bg_Black, 3)
        self.assertEqual(int.from_bytes(self.texts(view)[-1][7:9], 'big'), 216)
        # The independent dashboard still owns icon-relative, left-aligned positions.
        self.assertEqual(view._draw_dashboard_value.__name__, '_draw_dashboard_value')

    def test_shortened_stock_cell_width_has_no_residue_in_ideal_framebuffer(self):
        def render(values):
            view = self.screen()
            framebuffer = Framebuffer(PanelAssets())
            view.lcd._packet_observer = framebuffer
            view.lcd.clear(view.lcd.Color_Bg_Black)
            for value in values:
                view._draw_thermal_target(value, 102, view.lcd.Color_Bg_Black)
            view.lcd.update()
            return framebuffer.snapshot()[0].crop((184, 102, 240, 118))
        for old, new in ((250.5, 0), (100, 9), (9, 250.5)):
            with self.subTest(old=old, new=new):
                self.assertIsNone(ImageChops.difference(
                    render((old, new)), render((new,))).getbbox())


if __name__ == '__main__':
    unittest.main()
