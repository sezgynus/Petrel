import unittest
from types import SimpleNamespace
from maintenance_assessment_service import MaintenanceAssessment
from maintenance_heater import ThermalResult
from maintenance_assessment import observations

class AssessmentIntegrationTest(unittest.TestCase):
    def test_thermal_context_and_operation_survive_normalization(self):
        child = ThermalResult('H05','extruder','PASSED_USER','measured',True,
            (('heating_c_per_s',1.2),),conditions=(('target_c',60.),),operation_id='op')
        o = observations(child,1)[0]
        self.assertEqual(o.conditions,(('target_c',60.),))
        self.assertEqual(o.operation_id,'op')
        self.assertTrue(o.restored)

    def test_bounded_cache_and_epoch_clear(self):
        a = MaintenanceAssessment(1)
        state = SimpleNamespace(epoch=1,settings={})
        a.ingest(ThermalResult('H01','extruder','PASSED_USER','x'),1,state)
        a.ingest(ThermalResult('H05','extruder','PASSED_USER','x'),1,state)
        self.assertEqual(len(a._latest),1)
        state.epoch=2
        a.ingest(ThermalResult('H01','heater_bed','PASSED_USER','x'),1,state)
        self.assertEqual(list(a._latest),[('H01','heater_bed')])
        self.assertEqual(a.report(None,()),((),()))
        a.clear()
        self.assertFalse(a._latest)
