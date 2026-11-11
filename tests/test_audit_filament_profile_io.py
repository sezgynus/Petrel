import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from petrel.features.maintenance.discovery.discovery import MaintenanceSnapshot, CALIBRATION, _add
from petrel.features.maintenance.domains.filament.controller import MaintenanceFilamentController, filament_services
from petrel.features.maintenance.execution.workflow import FirmwareWorkflow
from test_maintenance_ui_services import DeferredWorker


class FilamentProfileIO(unittest.TestCase):
    def make(self):
        name='heater_generic dryer'
        snap=MaintenanceSnapshot(1,global_modes=_add(0,'E14',CALIBRATION),
            config_marker=1,service_key=('maintenance.dryer_profile',
                                       'maintenance.dryer_target:'+name))
        state=NS(objects=(name,),settings={},ready=True,epoch=1)
        p=NS(state=state,maintenance=NS(snapshot=snap))
        worker=DeferredWorker()
        return MaintenanceFilamentController(p,worker,NS()),worker

    def test_menu_uses_ready_target_tokens_without_profile_io(self):
        owner,_=self.make()
        with patch('petrel.features.maintenance.domains.filament.controller.profile',side_effect=AssertionError('UI disk read')):
            for _ in range(10):
                rows=owner.available()
                self.assertEqual([(r.feature_id,r.device) for r in rows],
                                 [('E14','heater_generic dryer')])

    def test_explicit_start_defers_profile_load_to_existing_worker(self):
        owner,worker=self.make()
        with patch('petrel.features.maintenance.domains.filament.controller.profile',return_value={'dryers':[]}) as profile, \
             patch.object(FirmwareWorkflow,'_prepare',return_value='prepared'):
            self.assertTrue(owner.start('E14','heater_generic dryer')[0])
            profile.assert_not_called()
            worker.run()
            profile.assert_called_once()
            self.assertEqual(owner._future.result(),'prepared')

    def test_ready_records_exact_dryer_targets_only(self):
        state=NS(objects=('heater_generic dryer','fan'),settings={})
        with patch('petrel.features.maintenance.domains.filament.controller.profile',return_value={'dryers':[
                {'object':'fan'},{'object':'heater_generic dryer'}]}):
            tokens=filament_services(state)
        self.assertIn('maintenance.dryer_target:heater_generic dryer',tokens)
        self.assertNotIn('maintenance.dryer_target:fan',tokens)

