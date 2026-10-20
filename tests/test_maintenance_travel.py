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
        self.assertEqual(d._maintenance_context.interval,30000*1000)
        self.assertIn('30000 metres',str(d._maintenance_screen()))

class ExistingAxisReminderTests(unittest.TestCase):
    def test_existing_axis_entries_offer_travel_without_duplicate_device_rows(self):
        from test_capabilities import display,snapshot
        for axis in 'xyz':
            with self.subTest(axis=axis):
                raw=snapshot();raw['objects'].append(OBJECT)
                raw['status'][OBJECT]=state().status[OBJECT]
                raw['settings']['stepper_'+axis]={'step_pin':'PA1','dir_pin':'PA2','rotation_distance':40}
                view=display(raw);view._maintenance_init()
                device='stepper_'+axis
                # Use the standard axis device emitted by the existing plans.
                view._maintenance_options=lambda:((NS(device=device),),())
                view._maintenance_page='service_devices'
                choices=view._maintenance_screen().choices
                self.assertEqual(sum(c.value==device for c in choices),1)
                self.assertFalse(any(c.value=='axis_'+axis for c in choices))
                view._maintenance_dispatch(next(c for c in choices if c.value==device))
                self.assertEqual(view._maintenance_page,'service_basis')
                choices=view._maintenance_screen().choices
                self.assertTrue(any(c.value==(device,'mechanical','travel_mm') for c in choices))
                view._maintenance_dispatch(next(c for c in choices if c.value==(device,'mechanical','travel_mm')))
                view._maintenance_dispatch(Choice('Review','service_review'))
                self.assertEqual(view._maintenance_context.device,device)
                self.assertEqual(view._maintenance_context.basis,'travel_mm')
                self.assertEqual(view._maintenance_context.interval,
                                 (10 if axis=='z' else 30000)*1000)
                self.assertNotIn('travel_mm',view.pd.maintenance_service_bases('stepper_'+axis+'1'))
                with patch.dict('os.environ',{'PETREL_AXIS_TRAVEL':'0'}):
                    self.assertNotIn('travel_mm',view.pd.maintenance_service_bases(device))

    def test_existing_axis_policy_resolves_counter_and_legacy_policy_keeps_anchor(self):
        from maintenance_usage import metric_counter
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_ui_records.Path.home',return_value=Path(folder)):
            worker=DeferredWorker()
            usage=dict(travel_mm={'axis_x':100.},travel_counter_id='a'*32,
                       available_metrics=(('axis_x','travel_mm'),))
            policies=(ServicePolicy('lubricate','stepper_x','travel_mm',1000,'user'),
                      ServicePolicy('lubricate','axis_x','travel_mm',1000,'user'))
            def call(operation,policy=None):
                f=request(worker,operation,policy=policy,devices=('stepper_x','axis_x'),usage_provider=lambda:usage)
                worker.run();return f.result()[0]
            for policy in policies: call('save_policy',policy)
            usage['travel_mm']['axis_x']=1200
            self.assertEqual([t[2] for t in call('load')],['due','due'])
            for policy in policies:
                self.assertEqual(metric_counter(usage,policy.device,'travel_mm'),1200)
                call('complete',policy)
            self.assertEqual(metric_counter(usage,'stepper_x1','travel_mm'),None)
            usage['available_metrics']=()
            self.assertEqual([t[2] for t in call('load')],['unknown','unknown'])
