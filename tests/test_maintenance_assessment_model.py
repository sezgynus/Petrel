import unittest
from dataclasses import replace
from petrel.features.maintenance.assessment.model import Evidence, Measurement, Finding, comparable

class AssessmentContractsTest(unittest.TestCase):
    def evidence(self, **kw):
        data = dict(feature='H05', device='extruder', method='sensor', status='PASSED',
            observed_at=1., measurements=(Measurement('heating_c_per_s', 1., 'degC/s'),),
            conditions=(('profile_version',1),('target_c',60.),('initial_band','cold'),
                        ('fan_state','off'),('hardware_revision','1')),
            config_digest='abc')
        data.update(kw)
        return Evidence(**data)

    def test_baseline_requires_same_conditions_and_identity(self):
        e = self.evidence()
        self.assertTrue(comparable(e,e))
        for changed in (replace(e,device='heater_bed'),replace(e,config_digest=''),
                        replace(e,conditions=()),replace(e,status='ERROR')):
            self.assertFalse(comparable(changed,e))
        self.assertFalse(comparable(e,replace(e,status='FAILED_METRIC')))

    def test_reject_nonfinite_duplicate_and_mutable_payload(self):
        for v in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):
                Measurement('x',v,'mm')
        for kw in ({'measurements':[]},
                   {'measurements':(Measurement('x',1,'mm'),Measurement('x',2,'mm'))},
                   {'conditions':(('x',{}),)}, {'observed_at':-1},
                   {'restored':1}):
            with self.assertRaises(ValueError):
                self.evidence(**kw)

    def test_information_and_user_findings_remain_distinct(self):
        self.assertEqual(self.evidence(method='information').method,'information')
        f = Finding('fan.rotation','fan','clear','fan.observed',confidence='user_verified')
        self.assertEqual(f.confidence,'user_verified')
        with self.assertRaises(ValueError):
            replace(f,state='PASSED')
