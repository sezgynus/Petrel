import unittest
from types import SimpleNamespace as NS
from maintenance_experience import grouped,result_summary,result_details,device_name

class MaintenanceExperienceTests(unittest.TestCase):
    def row(self,feature,device=None,method=1):
        return NS(feature_id=feature,device=device,method=method,visible=True)

    def test_capability_groups_hide_duplicates_and_leveling_only(self):
        rows=(self.row('H01','extruder'),self.row('H05','extruder'),
              self.row('H01','heater_bed'),self.row('P05',method=8),
              self.row('H02','extruder',8),self.row('M03',method=8))
        groups=grouped(rows)
        self.assertEqual([r.feature_id for r in groups[0][2]],['H01','H01'])
        self.assertEqual(groups[1][0],'motion')
        self.assertEqual(grouped(rows,True)[0][2][0].feature_id,'H02')
        self.assertEqual(grouped(()),())

    def test_performance_failure_is_not_hidden_by_procedure_acceptance(self):
        result=NS(status='FAILED_METRIC',reason='',components=(NS(feature_id='H07',status='FAILED_METRIC'),))
        heading,lines,tone=result_summary(result)
        self.assertEqual(tone,'attention')
        self.assertIn('overshoot',' '.join(lines))
        self.assertNotIn('cartridge failed',' '.join(lines))

    def test_technical_error_has_no_hardware_failure_conclusion(self):
        heading,lines,tone=result_summary(NS(status='ERROR',reason='read_failed'))
        self.assertIn('No hardware health conclusion.',lines)
        heading,lines,tone=result_summary(NS(status=None,reason='observed_information'))
        self.assertEqual(heading,'Information received')

    def test_unknown_restore_and_klipper_shaper_provenance_remain_visible(self):
        result=NS(feature_id='R02',status='PASSED',reason='measured',restore_verified=False,
                  evidence=(('peak_hz',40),('axis','X')))
        self.assertNotIn('peak hz',str(result_details(result)))
        self.assertIn('Restore verified: not proven',result_details(result))
        self.assertEqual(device_name('extruder1'),'Hotend 1')
