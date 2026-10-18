"""CI-only reference persistence and compatibility, with explicit operator consent."""
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch
from maintenance_heater import ThermalResult
from maintenance_reference import request
from test_maintenance_ui_services import DeferredWorker
from test_capabilities import display,snapshot
from maintenance_experience import Choice
from unittest.mock import Mock


def result(rate=1.,**conditions):
    values=dict(profile_version=1,target_c=60,duration_s=120,
        initial_temperature_c=22,fan_state='observed-off',firmware_version='test-v1')
    values.update(conditions)
    child=ThermalResult('H05','extruder','PASSED_USER','measured',True,
        (('heating_c_per_s',rate),),conditions=tuple(values.items()),operation_id='operation')
    return ThermalResult('H01','extruder','PASSED_USER','group',True,
        components=(child,),conditions=child.conditions,operation_id='operation')


class ReferenceTests(unittest.TestCase):
    def test_ui_requires_condition_confirmation_and_explicit_threshold(self):
        view=display(snapshot());view._maintenance_init();view.checkkey=view.MaintenanceMenu
        outcome=result()
        view._maintenance_result=outcome;view._maintenance_page='result'
        self.assertTrue(any(c.action=='reference' for c in view._maintenance_screen().choices))
        future=__import__('concurrent.futures',fromlist=['Future']).Future()
        view.pd.maintenance_reference=Mock(return_value=future)
        view._maintenance_dispatch(Choice('Reference','reference',outcome))
        view._maintenance_dispatch(Choice('Compare','reference_limit',outcome))
        view.pd.maintenance_reference.assert_not_called()
        view._maintenance_dispatch(view._maintenance_screen().choices[0])
        self.assertEqual(view._maintenance_page,'reference_confirm')
        self.assertIn('Same heater',str(view._maintenance_screen()))
        view.pd.maintenance_reference.assert_not_called()
        view._maintenance_dispatch(view._maintenance_screen().choices[1])
        view.pd.maintenance_reference.assert_called_once_with('compare',outcome,relative_limit=.2,confirmed=True)
        self.assertEqual(view._maintenance_page,'reference_wait')

    def test_reference_is_deferred_explicit_and_survives_worker_requests(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_reference.Path.home',return_value=Path(folder)):
            worker=DeferredWorker();state=NS(settings={})
            with self.assertRaises(ValueError): request(worker,'save',result(),state,current=lambda:True)
            save=request(worker,'save',result(),state,confirmed=True,current=lambda:True)
            self.assertFalse(save.done());worker.run()
            self.assertEqual(save.result().heading,'Heating reference saved')
            compare=request(worker,'compare',result(.5),state,confirmed=True,
                relative_limit=.2,current=lambda:True)
            worker.run();answer=compare.result()
            self.assertIn('slower',answer.heading)
            self.assertEqual(answer.finding.state,'attention')
            for changed in (dict(duration_s=60),dict(fan_state='observed-on'),
                            dict(initial_temperature_c=32),dict(firmware_version='v2')):
                f=request(worker,'compare',result(.5,**changed),state,confirmed=True,
                    relative_limit=.2,current=lambda:True)
                worker.run();self.assertEqual(f.result().heading,'No compatible reference')

    def test_missing_conditions_and_stale_session_never_create_reference(self):
        worker=DeferredWorker();state=NS(settings={})
        with self.assertRaises(ValueError):
            request(worker,'save',result(fan_state=''),state,confirmed=True,current=lambda:True)
        f=request(worker,'save',result(),state,confirmed=True,current=lambda:False)
        worker.run()
        with self.assertRaisesRegex(ValueError,'session_changed'): f.result()

    def test_hardware_change_can_explicitly_remove_reference(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_reference.Path.home',return_value=Path(folder)):
            worker=DeferredWorker();state=NS(settings={})
            for operation in ('save','clear'):
                f=request(worker,operation,result(),state,confirmed=True,current=lambda:True)
                worker.run();f.result()
            f=request(worker,'compare',result(),state,confirmed=True,relative_limit=.2,current=lambda:True)
            worker.run();self.assertEqual(f.result().heading,'No compatible reference')
