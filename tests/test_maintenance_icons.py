"""Semantic Graphite icons and small artwork contracts for Maintenance."""
import unittest
from types import SimpleNamespace as NS
from test_capabilities import display,snapshot
from maintenance_experience import Choice
from maintenance_icons import icon_for,feature_icon,TOPICS
from lcd_resources import (ICON_MAINTENANCE_CHECK,ICON_MAINTENANCE_DIAGNOSTICS,
    ICON_MAINTENANCE_RECOMMENDATIONS,ICON_MAINTENANCE_CARE)

class MaintenanceSemanticIcons(unittest.TestCase):
    def test_fixed_destinations_have_different_purpose_icons(self):
        choices=(Choice('Check','open','groups'),Choice('Data','open','diagnostic_groups'),
            Choice('Advice','findings'),Choice('Care','service'))
        self.assertEqual(tuple(map(icon_for,choices)),(164,165,166,167))

    def test_sensor_diagnostics_row_has_existing_sensor_icon(self):
        # The generic Sensors destination uses the library's endstop/switch icon.
        # Verify the real menu contract, not a label-based fallback.
        d=display(snapshot());d._maintenance_init();d._maintenance_page='diagnostic_groups'
        sensors=next(c for c in d._maintenance_screen().choices
                     if c.action=='open' and c.value=='sensor_devices')
        self.assertEqual(icon_for(sensors),30)
        self.assertEqual(icon_for(Choice('Sensors','open','sensor_devices')),30)

    def test_each_capability_family_uses_its_own_symbol(self):
        self.assertEqual(feature_icon('H01','heater_bed'),10)
        self.assertEqual(feature_icon('H01','extruder'),9)
        self.assertEqual(feature_icon('F02','fan'),48)
        self.assertEqual(feature_icon('M03','stepper_x'),29)
        self.assertEqual(feature_icon('P03','probe'),224)
        self.assertEqual(feature_icon('S18','buzzer'),214)
        self.assertNotIn(45,TOPICS.values())

    def test_unknown_and_data_rows_do_not_get_an_info_fallback(self):
        self.assertIsNone(icon_for(Choice('Unknown','open','unsupported')))
        self.assertIsNone(icon_for(Choice('Measurement: 12','none')))
        self.assertEqual(icon_for(Choice('Details','details')),45)

    def test_policy_task_uses_its_function(self):
        p=NS(task_id='lubricate')
        self.assertEqual(icon_for(Choice('Care','service_task',(p,None,'unknown'))),226)
        p.task_id='nozzle_inspect'
        self.assertEqual(icon_for(Choice('Care','service_task',(p,None,'unknown'))),38)

    def test_new_icons_are_small_baseline_420_and_inside_the_export(self):
        from pathlib import Path
        from PIL import Image,JpegImagePlugin
        from dwin_emulator.assets import PanelAssets
        root=Path(__file__).resolve().parents[1];assets=PanelAssets()
        for icon in (164,165,166,167):
            with Image.open(root/('assets/icons/%d.jpg'%icon)) as im:
                self.assertEqual(im.size,(20,20))
                self.assertEqual(JpegImagePlugin.get_sampling(im),2)
                self.assertFalse(im.info.get('progressive'))
            self.assertEqual(assets.icon(3,icon).size,(20,20))
            self.assertTrue((root/('assets/icon-source/%d.svg'%icon)).exists())

    def test_root_draws_purpose_icons_once_and_keeps_them_on_focus(self):
        d=display(snapshot());d._maintenance_init();d._maintenance_page='root'
        d.Draw_Maintenance_Menu()
        shown={c.args[1] for c in d.lcd.show_icon.call_args_list}
        self.assertTrue({164,165,166,167}<=shown)
        d.lcd.reset_mock();d._maintenance_selection=3;d.Draw_Maintenance_Menu()
        d.lcd.show_icon.assert_not_called()

if __name__=='__main__': unittest.main()
