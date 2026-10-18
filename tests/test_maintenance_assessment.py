import unittest
from types import SimpleNamespace
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, AUTOMATIC, _mode
from maintenance_planner import build_plan
from maintenance_heater import thermal_adapters, ThermalResult
from maintenance_assessment import assessment_plan, observations, assess

class AssessmentTest(unittest.TestCase):
    def plan(self):
        bits = sum(AUTOMATIC << (int(f[1:])+12)*5 for f in ()) # use discovery helper below
        from maintenance_discovery import _index_for
        bits = sum(AUTOMATIC << (_index_for(f)*5) for f in ('H01','H05','H07','H08'))
        snap = MaintenanceSnapshot(1,(DeviceCapabilities('extruder','heater',bits),),config_marker=2)
        return snap,assessment_plan(snap,build_plan(snap,thermal_adapters()))

    def test_combined_thermal_plan_deduplicates_execution(self):
        snap,plan = self.plan()
        self.assertEqual(plan[0].checks,('H01',))
        self.assertEqual(len(plan[0].rows),4)
        self.assertFalse(assessment_plan(None,plan[0].rows))
        self.assertFalse(assessment_plan(MaintenanceSnapshot(2),plan[0].rows))

    def test_missing_failed_and_information_are_not_global_health(self):
        _,plan = self.plan()
        self.assertTrue(all(f.state=='unknown' for f in assess(plan,())))
        result = ThermalResult('H01','extruder','FAILED_METRIC','group',
            components=(ThermalResult('H07','extruder','FAILED_METRIC','threshold',True,
                (('overshoot_c',8.),)),))
        obs = observations(result,1)
        findings = assess(plan,obs)
        f = next(f for f in findings if f.rule_id=='check.H07')
        self.assertEqual(f.state,'attention')
        self.assertEqual(f.actions,())
        self.assertNotIn('pid_bad',f.message_key)
        self.assertEqual(assess((),obs),())

    def test_technical_error_is_unknown_and_user_result_keeps_provenance(self):
        _,plan = self.plan()
        for status,expected in (('ERROR','unknown'),('BLOCKED','unknown'),
                                ('PASSED_USER','clear')):
            obs = observations(ThermalResult('H01','extruder',status,'reason'),1)
            f = next(f for f in assess(plan,obs) if f.rule_id=='check.H01')
            self.assertEqual(f.state,expected)
            if status=='PASSED_USER':
                self.assertEqual(f.confidence,'user_verified')
