import unittest
from maintenance_assessment import Observation
from maintenance_assessment_rules import observed_finding, metric_finding, MetricPolicy, trend_finding
from maintenance_assessment_model import Evidence, Measurement

class AssessmentRulesTest(unittest.TestCase):
    def item(self,feature,fields,status='OBSERVED'):
        return Observation(feature,None,status,'',16,tuple(fields),None)

    def test_active_and_historical_throttling_distinct(self):
        a = observed_finding(self.item('S03',[('throttled_bits',1)]))
        b = observed_finding(self.item('S03',[('throttled_bits',65536)]))
        self.assertNotEqual(a.message_key,b.message_key)
        self.assertIsNone(observed_finding(self.item('S03',[('throttled_bits',1)],'ERROR')))

    def test_explicit_metric_policy_and_missing_measurement(self):
        with self.assertRaises(ValueError):
            MetricPolicy('H07','overshoot_c',upper=5)
        p = MetricPolicy('H07','overshoot_c',upper=5,source='validated_profile')
        self.assertEqual(metric_finding(self.item('H07',[('overshoot_c',8)]),p).state,'attention')
        self.assertIsNone(metric_finding(self.item('H07',[]),p))
        self.assertIsNone(metric_finding(self.item('H07',[('overshoot_c',8)],'ERROR'),p))

    def test_comparable_trend_is_indicative_not_failure_diagnosis(self):
        conditions=(('profile_version',1),('target_c',60),('initial_band','25-26'),
                    ('fan_state','off'),('hardware_revision','a'))
        a=Evidence('H05','extruder','sensor','PASSED',1,
            (Measurement('rate',1,'degC/s'),),conditions,config_digest='a')
        b=Evidence('H05','extruder','sensor','PASSED',2,
            (Measurement('rate',2,'degC/s'),),conditions,config_digest='a')
        f=trend_finding(a,b,'rate',relative_limit=.2,source='profile')
        self.assertEqual(f.state,'attention')
        self.assertEqual(f.confidence,'indicative')
        self.assertIsNone(trend_finding(a,Evidence('H05','extruder','sensor','PASSED',0),
            'rate',relative_limit=.2,source='profile'))
