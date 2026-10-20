"""CI-only safe reminder removal: explicit UI intent and isolated persistence."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import tempfile
import unittest
from maintenance_assessment_store import AssessmentStore, ServicePolicy
from maintenance_ui_records import request
from test_maintenance_ui_services import DeferredWorker
from test_capabilities import display, snapshot
from maintenance_experience import Choice


class ReminderRemovalStore(unittest.TestCase):
    def test_remove_preserves_other_policies_tracking_history_and_baselines(self):
        with tempfile.TemporaryDirectory() as folder:
            store=AssessmentStore(Path(folder)/'assessment.json')
            policy=ServicePolicy('inspect_clean','fan','sampled_on_s',100,'user')
            other=replace(policy,device='extruder')
            for p in (policy,other):
                store.set_service_policy(p)
                store.begin_tracking(p,timestamp=10,counter=20,counter_id='ledger')
                store.complete_service(p,timestamp=30,confirmed=True,counter=40,counter_id='ledger')
            before=store.load()
            self.assertTrue(store.remove_service_policy(policy))
            after=store.load()
            self.assertEqual(store.service_policies(),(other,))
            for key in ('baselines','tracking','services'):
                self.assertEqual(after[key],before[key])
            self.assertFalse(store.remove_service_policy(policy))
            self.assertEqual(store.load(),after)

    def test_stale_confirmation_does_not_remove_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            store=AssessmentStore(Path(folder)/'assessment.json')
            old=ServicePolicy('inspect_clean','fan','calendar_s',100,'user')
            new=replace(old,interval=200)
            store.set_service_policy(new)
            with self.assertRaisesRegex(ValueError,'service_policy_changed'):
                store.remove_service_policy(old)
            self.assertEqual(store.service_policies(),(new,))

    def test_failed_atomic_save_does_not_report_deleted_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            store=AssessmentStore(Path(folder)/'assessment.json')
            policy=ServicePolicy('inspect_clean','fan','calendar_s',100,'user')
            store.set_service_policy(policy)
            with patch.object(store,'_save',side_effect=OSError('disk')):
                with self.assertRaises(OSError):store.remove_service_policy(policy)
            self.assertEqual(store.service_policies(),(policy,))

    def test_worker_removal_needs_no_live_device_or_usage_read(self):
        with tempfile.TemporaryDirectory() as folder, patch('maintenance_ui_records.Path.home',return_value=Path(folder)):
            store=AssessmentStore(Path(folder)/'.config/Petrel/maintenance-assessment.json')
            policy=ServicePolicy('inspect_clean','output_pin removed','sampled_on_s',100,'user')
            store.set_service_policy(policy)
            worker=DeferredWorker();usage=Mock(side_effect=AssertionError('usage read'))
            future=request(worker,'remove_policy',policy=policy,devices=(),usage_provider=usage)
            self.assertFalse(future.done())
            self.assertEqual(store.service_policies(),(policy,))
            worker.run()
            self.assertEqual(future.result(),((),()))
            usage.assert_not_called()
            self.assertEqual(store.service_policies(),())


class ReminderRemovalUI(unittest.TestCase):
    def view(self):
        view=display(snapshot());view._maintenance_init();view.checkkey=view.MaintenanceMenu
        view._maintenance_options=lambda:((NS(device='fan'),),())
        view.pd.maintenance_ui_records=Mock()
        policy=ServicePolicy('inspect_clean','fan','calendar_s',86400,'user')
        view._maintenance_page='service_task'
        view._maintenance_context=(policy,{'timestamp':10},'not_due')
        return view,policy

    def test_remove_requires_separate_confirmation_with_keep_selected(self):
        view,policy=self.view()
        choice=next(c for c in view._maintenance_screen().choices if c.action=='service_remove_confirm')
        view._maintenance_dispatch(choice)
        screen=view._maintenance_screen()
        self.assertEqual(view._maintenance_page,'service_remove_confirm')
        self.assertEqual(view._maintenance_selection,0)
        self.assertEqual(screen.choices[0].label,'Keep reminder')
        self.assertIn('Usage and service history stay.',screen.lines)
        view.pd.maintenance_ui_records.assert_not_called()
        view._maintenance_dispatch(screen.choices[0])
        self.assertEqual(view._maintenance_page,'service_task')
        view.pd.maintenance_ui_records.assert_not_called()

    def test_confirm_queues_once_then_returns_to_refreshed_schedule(self):
        from concurrent.futures import Future
        view,policy=self.view();future=Future()
        view.pd.maintenance_ui_records.return_value=future
        view._maintenance_dispatch(Choice('Remove','service_remove_confirm',policy))
        choice=view._maintenance_screen().choices[1]
        view._maintenance_dispatch(choice)
        view._maintenance_dispatch(choice)
        view.pd.maintenance_ui_records.assert_called_once_with('remove_policy',policy=policy,history=False)
        self.assertEqual(view._maintenance_page,'storage')
        future.set_result(((),()))
        view._poll_maintenance_ui()
        self.assertEqual(view._maintenance_page,'service')
        self.assertEqual(view._maintenance_records_data,((),()))
        self.assertTrue(view._maintenance_records_ready)

    def test_failure_is_visible_without_claiming_removal(self):
        from concurrent.futures import Future
        view,policy=self.view();future=Future()
        view.pd.maintenance_ui_records.return_value=future
        view._maintenance_dispatch(Choice('Remove','service_remove_confirm',policy))
        view._maintenance_dispatch(view._maintenance_screen().choices[1])
        future.set_exception(OSError('disk'))
        view._poll_maintenance_ui()
        self.assertEqual(view._maintenance_page,'notice')
        self.assertIn('No success is assumed.',view._maintenance_context[1])
