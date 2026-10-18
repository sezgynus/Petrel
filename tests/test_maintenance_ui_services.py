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
            self.assertEqual(tasks[0][2],'unknown');self.assertIsNone(tasks[0][1])
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

    def test_failed_record_future_is_not_success(self):
        d=self.view();future=Future();future.set_exception(OSError('disk full'))
        d._maintenance_records_future=future;d._maintenance_page='storage'
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page,'notice')
        self.assertFalse(d._maintenance_records_ready)

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
