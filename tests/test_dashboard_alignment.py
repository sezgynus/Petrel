"""All dashboard numbers share icon-relative anchors and bounded dirty areas."""
import unittest
from unittest.mock import patch
from test_capabilities import display,snapshot
from test_regressions import ui
from tools.render_docs_screenshots import canvas
from PIL import ImageChops


class DashboardAlignmentTests(unittest.TestCase):
    def values(self,v,wide):
        v.pd.thermalManager['temp_hotend'][0].update(celsius=259 if wide else 9,target=260 if wide else 0)
        v.pd.thermalManager['temp_bed'].update(celsius=100 if wide else 8,target=110 if wide else 0)
        v.pd.live_velocity=300 if wide else 0
        v.pd.volumetric_flow=99.9 if wide else 0
        v.pd.feedrate_percentage=100 if wide else 9
        v.pd.flow_percentage=100 if wide else 9
        v.pd.BABY_Z_VAR=-.125 if wide else 0
        v.pd.live_position=(-125.12,125.12,123.456) if wide else (1,2,.3)

    def test_all_nine_fields_keep_the_same_first_glyph_anchor_in_both_phases(self):
        v=display(snapshot(probe=True))
        for wide in (False,True):
            self.values(v,wide)
            v.pd.thermalManager['fan_speed'][0]=100 if wide else 0
            for phase in (0,2):
                v.lcd.reset_mock()
                with patch.object(ui.time,'monotonic',return_value=phase):
                    v.Draw_Status_Area(False)
                fields=[c.args for c in v.lcd.draw_text.call_args_list if c.args[6] in (380,414,448)]
                self.assertEqual(len(fields),9)
                for args in fields:
                    x,y,text=args[5:]
                    self.assertIn(x,(28,126,224))
                    self.assertTrue(text and not text.startswith(' '))
                    self.assertLessEqual(x+len(text)*8,{28:102,126:200,224:272}[x])
                temperatures=[a[-1] for a in fields if a[5]==28 and a[6]!=448]
                self.assertEqual(temperatures,['259/260','100/110'] if wide else ['9/0','8/0'])

    def test_shortening_values_matches_clean_pixels_without_redrawing_the_screen(self):
        v,reference=canvas(snapshot(probe=True)),canvas(snapshot(probe=True))
        with patch.object(ui.time,'monotonic',return_value=0):
            self.values(v,True)
            v.Draw_Status_Area(False)
            for wide in (False,True,False):
                self.values(v,wide);self.values(reference,wide)
                v.Draw_Status_Area(True)
                reference.Draw_Status_Area(False)
                # The emulator presents drawn packets only after an LCD update.
                v.lcd.update()
                reference.lcd.update()
                actual=v.framebuffer.snapshot()[0].crop((0,360,272,480))
                expected=reference.framebuffer.snapshot()[0].crop((0,360,272,480))
                self.assertIsNone(ImageChops.difference(actual,expected).getbbox())

    def test_extreme_external_values_stay_inside_their_column(self):
        v=display(snapshot())
        v._status_render={}
        for icon_x in (4,102,200):
            v._draw_dashboard_value('12345678901234567890',icon_x,448)
            args=v.lcd.draw_text.call_args.args
            self.assertEqual(args[5],icon_x+24)
            self.assertLessEqual(args[5]+len(args[-1])*8,min(272,icon_x+98))
            self.assertEqual(set(args[-1]),{'#'})
