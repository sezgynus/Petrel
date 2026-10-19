"""CI-only numeric parity, live field bounds and unchanged command payloads."""
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from display_numbers import fixed, js_round, setting_text, motion_text, clock_duration
from print_tuning import Setting
from preview_metadata import amount, duration, filament_length
from ui_bed_mesh import point_label
from test_capabilities import printer, display, snapshot
from test_regressions import ui
import test_print_tuning as tuning


class MainsailNumericDisplayTests(unittest.TestCase):
    def test_rounding_matches_javascript_runtime_at_binary_and_half_boundaries(self):
        values = [-30.5,-2.55,-.0001,-0.,.125,.49999999999999994,.5,1.005,2.25,
                  2.675,9.8,12.5,30.5,100.5,199.96,9999.9999]
        script = 'const v=JSON.parse(process.argv[1]);console.log(JSON.stringify(v.map(x=>[Math.round(x),...[0,1,2,3].map(n=>x.toFixed(n))])))'
        expected = json.loads(subprocess.check_output(['node','-e',script,json.dumps(values)],text=True))
        for value, row in zip(values,expected):
            with self.subTest(value=value):
                self.assertEqual(js_round(value),row[0])
                self.assertEqual([fixed(value,n) for n in range(4)],row[1:])

    def test_spool_percent_matches_ceiling_and_mainsail_total_weight_fallback(self):
        p = printer(snapshot())
        for remaining, expected in ((2.1,3),(39.2,40),(61,61),(57.1,58),(0,0)):
            self.assertEqual(p._spool_remaining_percent({'remaining_weight':remaining,'initial_weight':100}),expected)
        self.assertEqual(p._spool_remaining_percent({'remaining_weight':39.2,'filament':{'weight':100},'used_weight':960.8}),40)
        self.assertIsNone(p._spool_remaining_percent({'remaining_weight':39.2,'used_weight':60.8}))
        self.assertIsNone(p._spool_remaining_percent({'remaining_weight':1,'initial_weight':0,'filament':{'weight':100}}))

    def test_live_percentages_and_case_light_use_js_round(self):
        data = snapshot()
        data['status']['fan']['speed'] = .098
        data['status']['gcode_move'].update(speed_factor=1.005,extrude_factor=1.005)
        p = printer(data)
        self.assertEqual(p.thermalManager['fan_speed'][0],10)
        self.assertEqual(p.feedrate_percentage,js_round(1.005*100))
        self.assertEqual(p.flow_percentage,js_round(1.005*100))
        data['status']['output_pin case_light'] = {'value':.125}
        self.assertEqual(p.case_light_state(),(True,13))

    def test_tune_formats_and_commands_keep_raw_observations_separate(self):
        data = tuning.PrintTuningTests().data()
        data['status']['extruder'].update(pressure_advance=.1238,smooth_time=.0458,target=200.8)
        data['status']['toolhead'].update(square_corner_velocity=5.18)
        data['status']['firmware_retraction'].update(retract_length=2.38,unretract_extra_length=.238,
                                                    retract_speed=30.8,unretract_speed=25.8)
        p = printer(data)
        values = {s.key:s for s in p.print_settings()}
        for key, expected in {'pa@extruder':'0.123','smooth@extruder':'0.045s','nozzle@extruder':'200.8C',
                              'scv':'5.1mm/s','retract_length':'2.38mm','unretract_extra_length':'0.23mm',
                              'retract_speed':'30mm/s','unretract_speed':'25mm/s'}.items():
            self.assertEqual(setting_text(values[key],values[key].value),expected)
        self.assertEqual(values['pa@extruder'].value,.1238)
        p.set_print_setting('pa@extruder',.1238)
        p.sendGCode.assert_called_with('SET_PRESSURE_ADVANCE EXTRUDER=extruder ADVANCE=0.1238')
        for item in values.values():
            if not item.toggle:
                text = setting_text(item,item.value)
                self.assertGreaterEqual(260-len(text)*8,18+len(item.label)*8+8)

    def test_motion_labels_match_mainsail_without_changing_limits(self):
        for key,value,text in [('max_velocity',300.8,'300'),('max_accel',1000.8,'1000'),
                               ('square_corner_velocity',5.18,'5.1'),('minimum_cruise_ratio',.505,'51%')]:
            self.assertEqual(motion_text(key,value),text)

    def test_axis_offset_and_thermal_cells_stay_inside_existing_row(self):
        v = display(snapshot())
        v.lcd.reset_mock()
        for axis,value,expected in ((0,120.126,'120.13'),(1,-10.126,'-10.13'),(2,.306,'0.306')):
            v._draw_axis_value(axis,value*v.MINUNITMULT,90,v.lcd.Color_Bg_Black)
            args = v.lcd.draw_text.call_args.args
            self.assertEqual(args[-1].strip(),expected)
            self.assertEqual(args[5],216)
            self.assertLessEqual(args[5]+len(args[-1])*8,272)
        v._draw_offset_value(-20*100,90,v.lcd.Color_Bg_Black)
        self.assertEqual(v.lcd.draw_text.call_args.args[-1].strip(),'-20')
        self.assertLessEqual(202+len(v.lcd.draw_text.call_args.args[-1])*8,272)
        v._draw_thermal_target(200.8,90,v.lcd.Color_Bg_Black)
        self.assertEqual(v.lcd.draw_text.call_args.args[-1].strip(),'200.8')
        v._draw_axis_value(2,-100.123*v.MINUNITMULT,90,v.lcd.Color_Bg_Black)
        self.assertEqual(v.lcd.draw_text.call_args.args[-1].strip(),'-100.12')

    def test_dashboard_applies_xy_precision_and_preserves_narrow_exceptions(self):
        v = display(snapshot())
        v.lcd.DWIN_WIDTH=272;v.lcd.DWIN_HEIGHT=480
        v.pd.live_position=(120.126,-10.126,.306)
        v.pd.volumetric_flow=100.26
        with patch.object(ui.time,'monotonic',return_value=0):
            v.Draw_Status_Area(False)
        xyz = [c.args for c in v.lcd.draw_text.call_args_list if c.args[6]==448]
        self.assertEqual([args[-1].strip() for args in xyz],['120.13','-10.13','0.306'])
        for args,right in zip(xyz,(102,200,272)):
            self.assertLessEqual(args[5]+len(args[-1])*8,right)
        self.assertIn('100mm3/s',[c.args[-1] for c in v.lcd.draw_text.call_args_list])
        self.assertGreater(len('100.3mm3/s')*8,200-126)
        self.assertGreater(len('-20.000')*8,272-224)
        self.assertGreater(len('199.9/200.8')*8,102-28)

    def test_negative_flow_clamps_only_display_and_mmu_temperature_keeps_precision(self):
        data = snapshot()
        data['status']['extruder'].update(temperature=199.96,target=200.8)
        v = display(data)
        v.lcd.DWIN_WIDTH=272;v.lcd.DWIN_HEIGHT=480
        v.pd.volumetric_flow=-2.25
        with patch.object(ui.time,'monotonic',return_value=0):
            v.Draw_Status_Area(False)
        self.assertEqual(v.pd.volumetric_flow,-2.25)
        self.assertIn('0.0mm3/s',[c.args[-1] for c in v.lcd.draw_text.call_args_list])
        self.assertEqual(v._mmu_temperature_text(),'200.0/200.8 C')

    def test_duration_and_preview_metadata_match_units_and_fit_fixed_fields(self):
        self.assertEqual(clock_duration(3661),'1:01:01')
        self.assertLessEqual(len(clock_duration(10**11)),11)
        self.assertEqual(duration(12033),'3h 20m 33s')
        self.assertEqual(amount(22.41,'g'),'22g')
        self.assertEqual(filament_length(500.6),'501mm')
        self.assertEqual(filament_length(7512.75),'7.51m')
        self.assertLessEqual(len(duration(10**9)),14)

    def test_mesh_precision_only_added_when_existing_label_spacing_allows(self):
        self.assertEqual(point_label(.126,5),'0.126')
        self.assertEqual(point_label(-.126,5),'-0.126')
        self.assertEqual(point_label(-.126,8),'-0.13')
        self.assertEqual(point_label(.126,9),'.13')

    def test_unusual_tune_values_do_not_paint_over_labels(self):
        setting = Setting('z','Z offset','PRINT',1e100,0,1e101,.01,3,'mm')
        text = setting_text(setting,setting.value)
        self.assertGreaterEqual(260-len(text)*8,18+len(setting.label)*8+8)
