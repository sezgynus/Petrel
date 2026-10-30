"""CI-only measured maintenance progress and durable tracking baselines."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petrel.features.maintenance.assessment.store import AssessmentStore, ServicePolicy
from petrel.features.maintenance.ui.care import care_items
from petrel.features.maintenance.records.ui_requests import request
from test_maintenance_ui_services import DeferredWorker


class MeasuredMaintenanceProgress(unittest.TestCase):
    def run_request(self, worker, operation, policy=None, usage=None, devices=('fan',)):
        result=request(worker,operation,policy=policy,devices=devices,
                       usage_provider=lambda: usage if usage is not None else {})
        worker.run()
        return result.result()[0][0]

    def test_sampled_print_plan_starts_on_creation_and_progresses_without_service(self):
        with tempfile.TemporaryDirectory() as folder, patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            policy=ServicePolicy('inspect_clean','fan','sampled_print_s',20*3600,'user')
            usage={'counter_id':'ledger','sampled_print_s':8*3600,'sampled_on_s':{'fan':2*3600}}
            w=DeferredWorker()
            saved=self.run_request(w,'save_policy',policy,usage)
            self.assertEqual(saved[2],'unknown')
            self.assertNotIn('timestamp',saved[1])
            self.assertEqual(saved[1]['_sampled_elapsed_s'],0)
            item=care_items((saved,),{'fan'},100)[0]
            self.assertEqual(item.progress,0.)
            self.assertIn('0/20h recorded',item.detail)
            usage['sampled_print_s']+=3*3600
            loaded=self.run_request(DeferredWorker(),'load',usage=usage)
            self.assertEqual(loaded[2],'unknown')
            item=care_items((loaded,),{'fan'},100)[0]
            self.assertAlmostEqual(item.progress,.15)
            self.assertEqual(item.detail,'3/20h recorded')
            store=AssessmentStore(Path(folder)/'.config/Petrel/maintenance-assessment.json')
            self.assertEqual(store.load()['services'],[])
            self.assertEqual(store.tracking_start(policy)['counter'],8*3600)
            usage['sampled_print_s']+=17*3600
            due=self.run_request(DeferredWorker(),'load',usage=usage)
            self.assertEqual(due[2],'due')
            self.assertEqual(care_items((due,),{'fan'},100)[0].progress,1)

    def test_completed_service_resets_observed_progress_not_total_counter(self):
        with tempfile.TemporaryDirectory() as folder, patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            p=ServicePolicy('inspect_clean','fan','sampled_print_s',10*3600,'user')
            usage={'counter_id':'ledger','sampled_print_s':15*3600,'sampled_on_s':{}}
            worker=DeferredWorker()
            self.run_request(worker,'save_policy',p,usage)
            usage['sampled_print_s']+=5*3600
            before=self.run_request(worker,'load',usage=usage)
            self.assertAlmostEqual(care_items((before,),{'fan'},200)[0].progress,.5)
            after=self.run_request(worker,'complete',p,usage)
            self.assertEqual(after[1]['counter'],20*3600)
            self.assertEqual(after[1]['_sampled_elapsed_s'],0)
            self.assertEqual(care_items((after,),{'fan'},200)[0].progress,0)
            usage['sampled_print_s']+=3600
            self.assertAlmostEqual(care_items((
                self.run_request(DeferredWorker(),'load',usage=usage),),{'fan'},300)[0].progress,.1)

    def test_powered_component_progress_uses_own_counter_not_print_time(self):
        with tempfile.TemporaryDirectory() as folder, patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            p=ServicePolicy('nozzle_inspect','extruder','sampled_on_s',20*3600,'user')
            usage={'counter_id':'ledger','sampled_print_s':100*3600,'sampled_on_s':{'extruder':2*3600}}
            self.run_request(DeferredWorker(),'save_policy',p,usage,('extruder',))
            usage['sampled_print_s']+=20*3600
            usage['sampled_on_s']['extruder']+=7*3600
            item=care_items((self.run_request(DeferredWorker(),'load',usage=usage,
                devices=('extruder',)),),{'extruder'},100)[0]
            self.assertAlmostEqual(item.progress,.35)
            self.assertEqual(item.detail,'7/20h recorded')

    def test_counter_reset_or_identity_change_never_fabricates_progress(self):
        with tempfile.TemporaryDirectory() as folder, patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            p=ServicePolicy('inspect_clean','fan','sampled_print_s',3600,'user')
            usage={'counter_id':'a','sampled_print_s':1000,'sampled_on_s':{}}
            self.run_request(DeferredWorker(),'save_policy',p,usage)
            for identity,value in (('b',3000),('a',900)):
                usage.update(counter_id=identity,sampled_print_s=value)
                task=self.run_request(DeferredWorker(),'load',usage=usage)
                item=care_items((task,),{'fan'},100)[0]
                self.assertEqual(task[2],'unknown')
                self.assertIsNone(item.progress)
                self.assertEqual(item.detail,'Tracking paused')
            store=AssessmentStore(Path(folder)/'.config/Petrel/maintenance-assessment.json')
            self.assertEqual(store.tracking_start(p)['counter_id'],'a')

    def test_legacy_policy_without_reference_starts_at_first_read_not_past_usage(self):
        with tempfile.TemporaryDirectory() as folder, patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            p=ServicePolicy('inspect_clean','fan','sampled_print_s',20*3600,'user')
            store=AssessmentStore(Path(folder)/'.config/Petrel/maintenance-assessment.json')
            store.set_service_policy(p)
            usage={'counter_id':'legacy','sampled_print_s':8*3600,'sampled_on_s':{}}
            first=self.run_request(DeferredWorker(),'load',usage=usage)
            self.assertEqual(first[1]['_sampled_elapsed_s'],0)
            self.assertNotIn('timestamp',first[1])
            usage['sampled_print_s']+=4*3600
            item=care_items((self.run_request(DeferredWorker(),'load',usage=usage),),{'fan'},100)[0]
            self.assertAlmostEqual(item.progress,.2)
            self.assertEqual(item.detail,'4/20h recorded')

    def test_calendar_plan_starts_tracking_without_false_service_completion(self):
        with tempfile.TemporaryDirectory() as folder, patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            p=ServicePolicy('inspect_clean','fan','calendar_s',100,'user')
            with patch('petrel.features.maintenance.records.ui_requests.time',return_value=1000):
                task=self.run_request(DeferredWorker(),'save_policy',p)
            self.assertEqual(task[2],'not_due')
            self.assertNotIn('timestamp',task[1])
            self.assertEqual(task[1]['_tracking_started_at'],1000)
            self.assertAlmostEqual(care_items((task,),{'fan'},1050)[0].progress,.5)
            self.assertEqual(care_items((task,),{'fan'},1101)[0].state,'due')

    def test_interval_edit_does_not_reset_counter_anchor(self):
        with tempfile.TemporaryDirectory() as folder, patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            p=ServicePolicy('inspect_clean','fan','sampled_print_s',10*3600,'user')
            usage={'counter_id':'abc','sampled_print_s':10000,'sampled_on_s':{}}
            self.run_request(DeferredWorker(),'save_policy',p,usage)
            usage['sampled_print_s']=13600
            new=ServicePolicy('inspect_clean','fan','sampled_print_s',20*3600,'user')
            task=self.run_request(DeferredWorker(),'save_policy',new,usage)
            self.assertEqual(task[1]['_sampled_elapsed_s'],3600)
            self.assertAlmostEqual(care_items((task,),{'fan'},100)[0].progress,.05)


if __name__ == '__main__':
    unittest.main()
