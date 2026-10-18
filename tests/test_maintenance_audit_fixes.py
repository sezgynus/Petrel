"""CI regressions for cross-layer Maintenance source audit findings."""
from concurrent.futures import Future
from types import SimpleNamespace as NS
from time import monotonic
import unittest
from unittest.mock import Mock, patch
from maintenance_workflow import FirmwareWorkflow, SafetyViolation
from maintenance_filament import MaintenanceFilamentController


class RuntimeSafetyTests(unittest.TestCase):
    def test_positive_safety_violation_never_uses_queue_retry_grace(self):
        owner = FirmwareWorkflow(NS(), None, None)
        owner._phase = 'running'
        owner._deadline = monotonic()+100
        owner._current = Mock(return_value=True)
        owner._command = Future()
        owner._safety_future = Future()
        owner._safety_future.set_exception(SafetyViolation('dryer_thermal_limit'))
        owner._shutdown = Mock(return_value=None)
        owner._runtime_queue_refresh_pending = Mock(return_value=True)
        self.assertIsNone(owner.poll())
        owner._shutdown.assert_called_once_with('dryer_thermal_limit')
        owner._runtime_queue_refresh_pending.assert_not_called()

    def test_dryer_ceiling_and_target_drift_are_positive_safety_failures(self):
        owner = MaintenanceFilamentController(NS(), None, None)
        owner._row = NS(feature_id='E14',device='heater_generic dryer',epoch=1,config_marker=2)
        owner._dryer = Mock(return_value={'object':'heater_generic dryer','target':60,'ceiling':70})
        with patch('maintenance_workflow.read_queue_evidence',return_value=object()):
            for temperature,target in ((70,60),(65,80)):
                with self.subTest(temperature=temperature,target=target):
                    with patch('maintenance_filament.query',return_value=({'heater_generic dryer':{
                            'temperature':temperature,'target':target}},10)):
                        with self.assertRaisesRegex(SafetyViolation,'dryer_thermal_limit'):
                            owner.runtime_evidence()
