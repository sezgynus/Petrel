import tempfile
import unittest
from pathlib import Path
from maintenance_assessment_store import AssessmentStore, ServicePolicy, service_due
from maintenance_assessment_model import Evidence

class AssessmentStoreTest(unittest.TestCase):
    def reference(self):
        return Evidence('H05','extruder','sensor','PASSED',1.,
            conditions=(('profile_version',1),('target_c',60),('initial_band','cold'),
                ('fan_state','off'),('hardware_revision','1')),config_digest='digest')

    def test_baseline_explicit_persistent_and_invalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = AssessmentStore(Path(tmp)/'assessment.json')
            e = self.reference()
            with self.assertRaises(ValueError):
                s.set_baseline('heater',e)
            s.set_baseline('heater',e,confirmed=True)
            self.assertEqual(AssessmentStore(s.path).baseline('heater',e),e)
            s.invalidate_device('extruder')
            self.assertIsNone(s.baseline('heater',e))

    def test_service_requires_confirmation_and_preserves_counter_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = AssessmentStore(Path(tmp)/'assessment.json')
            p = ServicePolicy('lubrication','axis_z','travel_mm',100,'manufacturer')
            with self.assertRaises(ValueError):
                s.complete_service(p,timestamp=1)
            s.complete_service(p,timestamp=1,confirmed=True,counter=10,counter_id='epoch-a')
            self.assertEqual(s.load()['services'][0]['counter_id'],'epoch-a')

    def test_tracking_anchor_is_distinct_from_service_history_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=AssessmentStore(Path(tmp)/'assessment.json')
            policy=ServicePolicy('clean','fan','sampled_on_s',100,'user')
            start=store.begin_tracking(policy,timestamp=20,counter=50,counter_id='ledger')
            self.assertEqual(start['counter'],50)
            self.assertEqual(store.begin_tracking(policy,timestamp=80,counter=90,counter_id='ledger'),start)
            self.assertEqual(AssessmentStore(store.path).tracking_start(policy),start)
            self.assertEqual(store.load()['services'],[])
            store.complete_service(policy,timestamp=90,confirmed=True,counter=100,counter_id='ledger')
            self.assertEqual(store.latest_service('clean','fan','sampled_on_s')['counter'],100)
            self.assertEqual(store.tracking_start(policy),start)

    def test_partial_counter_never_proves_not_due(self):
        p = ServicePolicy('clean','fan','sampled_on_s',100,'user')
        kw = dict(now=200,current=60,previous=0,continuity=True,
                  counter_id='a',previous_counter_id='a')
        self.assertEqual(service_due(p,**kw),'unknown')
        self.assertEqual(service_due(p,**dict(kw,current=120)),'due')
        self.assertEqual(service_due(p,**dict(kw,current=120,previous_counter_id='b')),'unknown')
        self.assertEqual(service_due(p,**dict(kw,current=120,previous=130)),'unknown')

    def test_calendar_and_corruption_fail_closed(self):
        p = ServicePolicy('clean','fan','calendar_s',100,'manufacturer')
        self.assertEqual(service_due(p,now=200,last_at=50),'due')
        self.assertEqual(service_due(p,now=20,last_at=50),'unknown')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'assessment.json'
            path.write_text('{"version":99}',encoding='utf-8')
            with self.assertRaises(ValueError):
                AssessmentStore(path).load()
