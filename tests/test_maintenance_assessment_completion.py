import tempfile
import unittest
from pathlib import Path
from maintenance_assessment_store import AssessmentStore, ServicePolicy
from maintenance_assessment_messages import message_text
from maintenance_assessment import Observation, assess, assessment_plan
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, CALIBRATION, _index_for
from maintenance_heater import thermal_adapters
from maintenance_planner import build_plan

class AssessmentCompletionTest(unittest.TestCase):
    def test_service_policy_survives_reload_and_does_not_acknowledge_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=AssessmentStore(Path(tmp)/'state.json')
            p=ServicePolicy('clean','fan','calendar_s',100,'manufacturer')
            s.set_service_policy(p)
            self.assertEqual(s.service_policies(),(p,))
            self.assertIsNone(s.latest_service('clean','fan'))
            s.complete_service(p,timestamp=1,confirmed=True)
            self.assertEqual(s.latest_service('clean','fan')['timestamp'],1)

    def test_calibration_completion_is_not_hardware_health_clear(self):
        bits=CALIBRATION << (_index_for('H02')*5)
        snap=MaintenanceSnapshot(1,(DeviceCapabilities('extruder','heater',bits),),config_marker=2)
        plan=assessment_plan(snap,build_plan(snap,thermal_adapters()))
        obs=Observation('H02','extruder','PASSED_USER','',8,(),True)
        f=assess(plan,(obs,))[0]
        self.assertEqual(f.state,'unknown')
        self.assertEqual(f.message_key,'calibration.completed')
        self.assertIn('Kalibrasyon',message_text(f.message_key,'tr'))
        self.assertNotEqual(message_text(f.message_key,'en'),message_text(f.message_key,'tr'))
