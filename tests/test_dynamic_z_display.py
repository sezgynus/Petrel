"""Adaptive Z precision, bounded redraws and retained raw observations."""
import unittest
from unittest.mock import patch
from display_numbers import fit_decimal
from test_capabilities import display, snapshot
from test_regressions import ui


class DynamicZDisplayTests(unittest.TestCase):
    def test_precision_falls_only_as_far_as_required_including_rounding_carry(self):
        for value,text in ((.306,'0.306'),(12.34,'12.34'),(125,'125'),
                           (-.125,'-0.125'),(-12.345,'-12.35'),
                           (123.456,'123.46'),(1234.567,'1234.6'),
                           (999.9999,'1000'),(-.0001,'0'),(1e20,'######')):
            with self.subTest(value=value):
                self.assertEqual(fit_decimal(value,6),text)
                self.assertLessEqual(len(text),6)

    def test_raw_values_stay_unchanged_and_formatting_is_cached_per_field(self):
        v=display(snapshot(probe=True))
        v.pd.live_position=(0,0,.306)
        v.pd.BABY_Z_VAR=-.125
        with patch.object(ui,'fit_decimal',wraps=fit_decimal) as formatter, patch.object(ui.time,'monotonic',return_value=0):
            v.Draw_Status_Area(False)
            self.assertEqual(formatter.call_count,2)
            v.lcd.reset_mock()
            v.Draw_Status_Area(True)
            self.assertEqual(formatter.call_count,2)
            self.assertFalse([c for c in v.lcd.draw_text.call_args_list if c.args[5]==224])
            v.pd.live_position=(0,0,123.456)
            v.Draw_Status_Area(True)
            self.assertEqual(formatter.call_count,3)
        self.assertEqual(v.pd.live_position[2],123.456)
        self.assertEqual(v.pd.BABY_Z_VAR,-.125)
        self.assertEqual(len(v._status_decimal_values),2)

    def test_shrinking_and_precision_changes_clear_only_the_existing_field(self):
        v=display(snapshot(probe=True))
        v.lcd.font8x16=1
        v._status_render={}
        for y in (414,448):
            v._draw_status_decimal(-.125,224,y)
            v.lcd.reset_mock()
            v._draw_status_decimal(0,224,y)
            v.lcd.draw_rectangle.assert_called_once_with(1,0x18C4,224,y,271,y+15)
            args=v.lcd.draw_text.call_args.args
            self.assertEqual(args[-1],'0     ')
            self.assertEqual(args[5],224)
            self.assertLessEqual(args[5]+len(args[-1])*8,272)
