import unittest
from dataclasses import replace
from types import SimpleNamespace
from maintenance_assessment import Observation, observations
from maintenance_assessment_bridge import typed_evidence, saved_evidence
from maintenance_assessment_model import comparable
from maintenance_physical import MaintenancePulseController

class AssessmentBridgeTest(unittest.TestCase):
    def test_units_explicit_and_conditions_not_invented(self):
        o=Observation('H05','extruder','PASSED_USER','',1,
            (('heating_c_per_s',1.2),('unknown_numeric',99)),True,
            (('target_c',60),),'operation')
        e=typed_evidence(o,observed_at=1,config_digest='a')
        self.assertEqual(e.measurements[0].unit,'degC/s')
        self.assertEqual(len(e.measurements),1)
        self.assertFalse(comparable(e,e))
        with self.assertRaises(ValueError):
            typed_evidence(o,observed_at=1,verified_conditions=(('target_c',80),))

    def test_legacy_record_readable_but_not_reference(self):
        e=saved_evidence(dict(feature='H05',device='extruder',status='PASSED',
            method=1,timestamp=1,evidence=[['heating_c_per_s',1.2]]))
        self.assertFalse(comparable(e,e))

    def test_f12_threshold_is_structured_not_reason_parsing(self):
        runner=object.__new__(MaintenancePulseController)
        runner._row=SimpleNamespace(feature_id='F12',device='fan')
        runner._f12_bracket=SimpleNamespace(low=50,high=51)
        runner._release=lambda:None
        result=runner._finish('PASSED_USER','human-readable reason',True)
        fields=dict(observations(result,2)[0].evidence)
        self.assertEqual(fields['pwm_lower'],50)
        self.assertEqual(fields['pwm_upper'],51)
        self.assertTrue(fields['user_verified'])

    def test_unknown_conditions_cannot_establish_reference(self):
        o=Observation('H05','extruder','PASSED','',1,(),True)
        e=typed_evidence(o,observed_at=1,config_digest='a',verified_conditions=(
            ('profile_version',1),('target_c',60),('initial_band','cold'),
            ('fan_state','unknown'),('hardware_revision','a')))
        self.assertFalse(comparable(e,e))
