import tempfile
import unittest
from pathlib import Path
from petrel.features.maintenance.assessment.store import AssessmentStore, ServicePolicy
from petrel.features.maintenance.assessment.messages import message_text
from petrel.features.maintenance.assessment.assessment import Observation, assess, assessment_plan
from petrel.features.maintenance.discovery.discovery import MaintenanceSnapshot, DeviceCapabilities, CALIBRATION, _index_for
from petrel.features.maintenance.domains.thermal.controller import thermal_adapters
from petrel.features.maintenance.execution.planner import build_plan

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
