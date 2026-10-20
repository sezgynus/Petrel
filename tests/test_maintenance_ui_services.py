import unittest
import tempfile
from pathlib import Path
from concurrent.futures import Future
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from test_capabilities import display,snapshot
from maintenance_experience import Choice
from maintenance_assessment_store import ServicePolicy
from maintenance_ui_records import request

class DeferredWorker:
    def __init__(self): self.work=[]
    def submit(self,fn,**kwargs):
        f=Future();self.work.append((fn,f));return f
    def run(self):
        fn,f=self.work.pop(0)
        try:f.set_result(fn())
        except Exception as e:f.set_exception(e)

class MaintenanceServiceUI(unittest.TestCase):
    def view(self):
        d=display(snapshot());d.checkkey=d.MaintenanceMenu;d._maintenance_init()
        d.pd.maintenance_pulse=NS(pending=False,phase=None,available=lambda:())
        d.get_encoder_state=Mock(return_value=d.ENCODER_DIFF_ENTER)
        return d

    def test_policy_save_does_not_claim_service_completed(self):
        with tempfile.TemporaryDirectory() as folder,patch('maintenance_ui_records.Path.home',return_value=Path(folder)):
            worker=DeferredWorker();p=ServicePolicy('inspect_clean','fan','calendar_s',86400,'user')
            f=request(worker,'save_policy',policy=p,devices=('fan',))
            self.assertFalse(f.done());worker.run()
            tasks,records=f.result()
            self.assertEqual(tasks[0][2],'not_due')
            self.assertIsNone(tasks[0][1].get('timestamp'))
            self.assertIsNotNone(tasks[0][1]['_tracking_started_at'])
            f=request(worker,'complete',policy=p,devices=('fan',));worker.run()
            tasks,records=f.result();self.assertEqual(tasks[0][2],'not_due')
            self.assertIsNotNone(tasks[0][1]['timestamp'])

    def test_removed_device_cannot_receive_new_service_record(self):
        worker=DeferredWorker();p=ServicePolicy('inspect_clean','missing','calendar_s',86400,'user')
        with self.assertRaises(ValueError): request(worker,'complete',policy=p,devices=('fan',))
        self.assertFalse(worker.work)

    def test_load_and_draw_do_not_touch_disk_on_ui_owner(self):
        d=self.view();future=Future();d.pd.maintenance_ui_records=Mock(return_value=future)
        d._maintenance_page='service';d.Draw_Maintenance_Menu()
        d.pd.maintenance_ui_records.assert_not_called()
        d._maintenance_dispatch(Choice('Load','load_services'))
        self.assertEqual(d._maintenance_page,'storage')
        d.pd.maintenance_ui_records.assert_called_once_with('load',policy=None,history=False)
        future.set_result(((),()))
        d._poll_maintenance_ui();self.assertEqual(d._maintenance_page,'service')
        self.assertTrue(d._maintenance_records_ready)

    def test_interval_editor_requires_review_and_separate_save(self):
        d=self.view();d._maintenance_page='service_interval'
        d._maintenance_context=('fan','inspect_clean',30)
        d.pd.maintenance_ui_records=Mock()
        d.get_encoder_state.return_value=d.ENCODER_DIFF_CW
        d.HMI_Maintenance_Menu();self.assertEqual(d._maintenance_context[2],31)
        d.get_encoder_state.return_value=d.ENCODER_DIFF_ENTER;d.HMI_Maintenance_Menu()
        self.assertEqual(d._maintenance_page,'service_review')
        d.pd.maintenance_ui_records.assert_not_called()
        self.assertEqual(d._maintenance_context.interval,31*86400)

    def test_calendar_due_is_recomputed_in_the_same_living_ui(self):
        d=self.view();d._maintenance_page='service'
        p=ServicePolicy('inspect_clean','fan','calendar_s',100,'user')
        d._maintenance_options=Mock(return_value=((NS(device='fan'),),()))
        d._maintenance_records_data=(((p,{'timestamp':10},'not_due'),),())
        d._maintenance_records_identity=d._maintenance_identity()
        d._maintenance_records_ready=True
        with patch.dict(d._maintenance_service_screen.__globals__,{'time':lambda:50}):
            self.assertIn('Within your interval',str(d._maintenance_screen()))
        with patch.dict(d._maintenance_service_screen.__globals__,{'time':lambda:110}):
            self.assertIn('Service is due',str(d._maintenance_screen()))
        self.assertTrue(any(c.action=='load_services' for c in d._maintenance_screen().choices))

    def test_discovery_change_invalidates_loaded_service_records(self):
        d=self.view();d._maintenance_page='service'
        d._maintenance_records_ready=True
        d._maintenance_records_identity=('old',1)
        screen=d._maintenance_screen()
        self.assertFalse(d._maintenance_records_ready)
        self.assertTrue(any(c.action=='load_services' for c in screen.choices))

    def test_failed_record_future_is_not_success(self):
        d=self.view();future=Future();future.set_exception(OSError('disk full'))
        d._maintenance_records_future=future;d._maintenance_page='storage'
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page,'notice')
        self.assertFalse(d._maintenance_records_ready)

    def test_usage_reminder_requires_basis_interval_review_and_explicit_save(self):
        d=self.view()
        d.pd.maintenance_service_bases=Mock(return_value=('calendar_s','sampled_print_s'))
        d.pd.maintenance_ui_records=Mock(return_value=Future())
        d._maintenance_dispatch(Choice('Lubricate','service_kind',('stepper_z','lubricate')))
        self.assertEqual(d._maintenance_page,'service_basis')
        choice=next(c for c in d._maintenance_screen().choices if c.value==('stepper_z','lubricate','sampled_print_s'))
        d._maintenance_dispatch(choice)
        d._maintenance_dispatch(d._maintenance_screen().choices[0])
        policy=d._maintenance_context
        self.assertEqual(policy.basis,'sampled_print_s')
        self.assertEqual(policy.interval,500*3600)
        d.pd.maintenance_ui_records.assert_not_called()
        d._maintenance_dispatch(next(c for c in d._maintenance_screen().choices if c.action=='service_save'))
        d.pd.maintenance_ui_records.assert_called_once_with('save_policy',policy=policy,history=False)

    def test_new_reminder_defaults_depend_on_device_task_and_metric(self):
        d=self.view()
        cases=(
            ('stepper_x','mechanical','travel_mm',30000,30000*1000),
            ('stepper_z','mechanical','travel_mm',10,10*1000),
            ('endstop stepper_x','sensor','trigger_count',500,500),
            ('probe','sensor','trigger_count',2000,2000),
            ('extruder','nozzle','calendar_s',30,30*86400),
            ('extruder','heating','sampled_on_s',300,300*3600),
            ('output_pin any','connected_device','calendar_s',180,180*86400),
            ('output_pin any','connected_device','sampled_print_s',500,500*3600),
            ('output_pin any','connected_device','sampled_on_s',500,500*3600),
        )
        for device,task,basis,amount,stored in cases:
            with self.subTest(device=device,task=task,basis=basis):
                d._maintenance_dispatch(Choice('Select','service_basis',(device,task,basis)))
                self.assertEqual(d._maintenance_page,'service_interval')
                self.assertEqual(d._maintenance_context,(device,task,amount,basis))
                d._maintenance_dispatch(Choice('Review','service_review'))
                self.assertEqual(d._maintenance_context.interval,stored)

    def test_usage_due_survives_render_and_coverage_remains_visible(self):
        d=self.view();d._maintenance_page='service'
        p=ServicePolicy('lubricate','stepper_z','sampled_print_s',100,'user')
        d._maintenance_options=Mock(return_value=((NS(device='stepper_z'),),()))
        d._maintenance_records_ready=True;d._maintenance_records_identity=d._maintenance_identity()
        d._maintenance_records_data=(((p,{'timestamp':10,'counter':0,'counter_id':'a'},'due'),),())
        screen=d._maintenance_screen()
        self.assertIn('Service is due',str(screen))
        d._maintenance_dispatch(next(c for c in screen.choices if c.action=='service_task'))
        self.assertIn('lower bound',str(d._maintenance_screen()))

    def test_maintenance_entry_invalidates_prior_screen_cache(self):
        d=self.view();d.Draw_Maintenance_Menu();d.lcd.reset_mock()
        d.Enter_Maintenance_Menu()
        d.lcd.show_icon.assert_called()
        self.assertEqual(d._maintenance_page,'root')

    def test_home_tiles_are_not_erased_by_absent_colour_patch(self):
        d=self.view();d.Draw_Maintenance_Menu()
        patches=[c for c in d.lcd.draw_rectangle.call_args_list if c.args[-4:]==(16,199,255,222)]
        self.assertEqual(patches,[])

    def test_history_is_explicitly_labelled_historical(self):
        d=self.view();r=dict(feature='H07',device='extruder',status='FAILED_METRIC',timestamp=1,
                            evidence=[['overshoot_c',7.72]],reason='thermal metric')
        d._maintenance_dispatch(Choice('Record','historical_result',r))
        self.assertEqual(d._maintenance_page,'details')
        self.assertIn('Historical',str(d._maintenance_screen()))

    def test_recent_history_back_preserves_parent_for_empty_and_saved_records(self):
        record=dict(feature='H07',device='extruder',status='FAILED_METRIC',timestamp=1,
                    evidence=[['overshoot_c',7.72]],reason='thermal metric')
        for records in ((),(record,)):
            with self.subTest(records=bool(records)):
                d=self.view();d._maintenance_show('root')
                d._maintenance_open('diagnostic_groups');d._maintenance_open('history')
                d._maintenance_selection=1
                ancestors=list(d._maintenance_history)
                for attempt in range(2):
                    future=Future();d.pd.maintenance_ui_records=Mock(return_value=future)
                    d._maintenance_dispatch(Choice('Recent check history','load_history'))
                    self.assertEqual(d._maintenance_page,'storage')
                    future.set_result(((),records));d._poll_maintenance_ui()
                    self.assertEqual(d._maintenance_page,'history_records')
                    if records:
                        d._maintenance_dispatch(d._maintenance_screen().choices[1])
                        self.assertEqual(d._maintenance_page,'details')
                        d._maintenance_dispatch(Choice('Back','back'))
                        self.assertEqual(d._maintenance_page,'history_records')
                    d._maintenance_dispatch(Choice('Back','back'))
                    self.assertEqual(d._maintenance_page,'history')
                    self.assertEqual(d._maintenance_selection,1)
                    self.assertEqual(d._maintenance_history,ancestors)

    def test_leaving_history_load_before_completion_does_not_redirect_or_pop_parent(self):
        d=self.view();d._maintenance_show('root')
        d._maintenance_open('diagnostic_groups');d._maintenance_open('history')
        ancestors=list(d._maintenance_history)
        future=Future();d.pd.maintenance_ui_records=Mock(return_value=future)
        d._maintenance_dispatch(Choice('Recent check history','load_history'))
        d._maintenance_dispatch(Choice('Back','back'))
        future.set_result(((),()));d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page,'history')
        self.assertEqual(d._maintenance_history,ancestors)

