"""CI-only lower-bound usage continuity and maintenance completion records."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from maintenance_records import MaintenanceBook
from maintenance_assessment_store import ServicePolicy
from maintenance_ui_records import request
from test_maintenance_ui_services import DeferredWorker


class UsageServiceTests(unittest.TestCase):
    def test_print_samples_survive_restart_as_a_lower_bound_with_ledger_identity(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_records.Path.home',return_value=Path(folder)):
            book=MaintenanceBook(DeferredWorker())
            state=NS(ready=True,epoch=1,settings={},status={'print_stats':{'state':'printing'},
                'virtual_sdcard':{'is_active':True},'pause_resume':{'is_paused':False}})
            for now in (0.,1.,2.,3.): book.note(state,now=now)
            first=book.service_counters()
            self.assertEqual(first['sampled_print_s'],3.)
            second=MaintenanceBook(DeferredWorker()).service_counters()
            self.assertEqual(second['sampled_print_s'],3.)
            self.assertEqual(second['counter_id'],first['counter_id'])
            state.status['pause_resume']['is_paused']=True
            book.note(state,now=4.)
            self.assertEqual(book.service_counters()['sampled_print_s'],3.)

    def test_sampled_reminder_due_requires_matching_ledger_and_completion_counter(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_ui_records.Path.home',return_value=Path(folder)):
            worker=DeferredWorker();usage={'counter_id':'ledger-a','sampled_print_s':10.,'sampled_on_s':{'fan':20.}}
            policy=ServicePolicy('lubricate','stepper_z','sampled_print_s',100.,'user')
            def call(op):
                f=request(worker,op,policy=policy if op!='load' else None,devices=('stepper_z',),
                    usage_provider=lambda:usage)
                worker.run();return f.result()[0][0]
            self.assertEqual(call('save_policy')[2],'unknown')
            self.assertEqual(call('complete')[1]['counter'],10.)
            usage['sampled_print_s']=50.
            self.assertEqual(call('load')[2],'unknown')
            usage['sampled_print_s']=110.
            self.assertEqual(call('load')[2],'due')
            usage['counter_id']='ledger-b'
            self.assertEqual(call('load')[2],'unknown')

    def test_calendar_completion_does_not_seed_a_different_usage_basis(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_ui_records.Path.home',return_value=Path(folder)):
            worker=DeferredWorker();calendar=ServicePolicy('inspect_clean','fan','calendar_s',100,'user')
            for op in ('save_policy','complete'):
                f=request(worker,op,policy=calendar,devices=('fan',));worker.run();f.result()
            hours=ServicePolicy('inspect_clean','fan','sampled_on_s',100,'user')
            f=request(worker,'save_policy',policy=hours,devices=('fan',),usage_provider=lambda:{
                'counter_id':'ledger','sampled_on_s':{'fan':1000}})
            worker.run();task=f.result()[0][0]
            self.assertIsNone(task[1]);self.assertEqual(task[2],'unknown')
