import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from maintenance_records import MaintenanceBook
from maintenance_travel import OBJECT, AXES
from maintenance_assessment_store import ServicePolicy
from maintenance_ui_records import request
from maintenance_care_view import care_items
from test_maintenance_ui_services import DeferredWorker
from maintenance_experience import Choice


def state(session='a'*32,x=0.,ready=True):
    return NS(ready=ready,epoch=1,settings={},objects=(OBJECT,),status={OBJECT:dict(
        session_id=session,x_mm=x,y_mm=0.,z_mm=0.,state='tracking')})


class TravelLedgerTests(unittest.TestCase):
    def test_restart_reconnect_session_change_and_disabled_preserve_totals(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_records.Path.home',return_value=Path(folder)):
            book=MaintenanceBook(DeferredWorker());book.note(state(x=100),0)
            first=book.service_counters()
            self.assertEqual(first['travel_mm']['axis_x'],100)
            book=MaintenanceBook(DeferredWorker());book.note(state(x=150),0)
            self.assertEqual(book.service_counters()['travel_mm']['axis_x'],150)
            # Two sessions before the periodic flush must both survive.
            book.note(state('b'*32,20),1);book.note(state('c'*32,30),2)
            final=book.service_counters()
            self.assertEqual(final['travel_mm']['axis_x'],200)
            self.assertEqual(first['travel_counter_id'],final['travel_counter_id'])
            book.note(state(ready=False),3)
            stopped=book.service_counters()
            self.assertEqual(stopped['travel_mm']['axis_x'],200)
            self.assertNotIn(('axis_x','travel_mm'),stopped['available_metrics'])

    def test_failed_save_retries_without_loss_or_double_count(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_records.Path.home',return_value=Path(folder)):
            book=MaintenanceBook(DeferredWorker());book.note(state(x=100),0)
            with patch('maintenance_records.write_json',side_effect=OSError('full')):
                with self.assertRaises(OSError): book.service_counters()
            self.assertEqual(book.service_counters()['travel_mm']['axis_x'],100)
            self.assertEqual(book.service_counters()['travel_mm']['axis_x'],100)

    def test_option_off_and_invalid_values_do_not_consume_counters(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_records.Path.home',return_value=Path(folder)):
            book=MaintenanceBook(DeferredWorker())
            with patch.dict('os.environ',{'PETREL_AXIS_TRAVEL':'0'}): book.note(state(x=100),0)
            self.assertEqual(book.service_counters()['travel_mm'],{})
            bad=state();bad.status[OBJECT]['x_mm']=float('nan');book.note(bad,1)
            self.assertEqual(book.service_counters()['travel_mm'],{})

    def test_distance_policy_due_completion_pause_and_reenable(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_ui_records.Path.home',return_value=Path(folder)):
            worker=DeferredWorker();policy=ServicePolicy('lubricate','axis_x','travel_mm',1000,'user')
            usage=dict(travel_mm={'axis_x':100.},travel_counter_id='a'*32,
                       available_metrics=(('axis_x','travel_mm'),))
            devices=AXES
            def call(operation):
                f=request(worker,operation,policy=policy if operation!='load' else None,
                          devices=devices,usage_provider=lambda:usage)
                worker.run();return f.result()[0][0]
            self.assertEqual(call('save_policy')[2],'unknown')
            usage['travel_mm']['axis_x']=1200
            self.assertEqual(call('load')[2],'due')
            self.assertEqual(call('complete')[1]['counter'],1200)
            usage['available_metrics']=();devices=()
            task=call('load')
            self.assertEqual(task[2],'unknown')
            self.assertEqual(care_items((task,),(),0)[0].detail,'Tracking paused')
            usage['available_metrics']=(('axis_x','travel_mm'),);devices=AXES
            usage['travel_mm']['axis_x']=2200
            self.assertEqual(call('load')[2],'due')

    def test_distance_interval_review_uses_metres_not_hours(self):
        from test_maintenance_ui_services import MaintenanceServiceUI
        d=MaintenanceServiceUI().view()
        d._maintenance_dispatch(Choice('Travel','service_basis',('axis_x','lubricate','travel_mm')))
        self.assertIn('metres travelled',str(d._maintenance_screen()))
        d._maintenance_dispatch(Choice('Review','service_review'))
        self.assertEqual(d._maintenance_context.interval,30000)
        self.assertIn('30 metres',str(d._maintenance_screen()))
