"""CI regressions for cross-layer Maintenance source audit findings."""
from concurrent.futures import Future
from types import SimpleNamespace as NS
from time import monotonic
import unittest
from unittest.mock import Mock, patch
from maintenance_workflow import FirmwareWorkflow, SafetyViolation
from maintenance_filament import MaintenanceFilamentController
from maintenance_test_trace import PrinterProxy
from printerInterface import PrinterData
from maintenance_physical import PhysicalResult
from maintenance_records import MaintenanceBook
from maintenance_discovery import discover, CALIBRATION


class ConfigOnlyDiscoveryTests(unittest.TestCase):
    def test_loaded_config_only_calibrations_do_not_need_status_objects(self):
        state=NS(ready=True,epoch=1,
            objects=('toolhead','gcode_move','probe','manual_probe'),status={},
            settings={'delta_calibrate':{'radius':50},
                      'axis_twist_compensation':{'calibrate_start_x':10}})
        snapshot=discover(state)
        self.assertEqual(snapshot.method('P16'),CALIBRATION)
        self.assertEqual(snapshot.method('P17'),CALIBRATION)
        self.assertNotIn('delta_calibrate',state.objects)
        self.assertNotIn('axis_twist_compensation',state.objects)


class RecordWriteTests(unittest.TestCase):
    def state(self):
        return NS(settings={},epoch=1,software_version='test')

    def test_failed_admission_future_is_counted_immediately(self):
        future=Future();future.set_exception(OSError('queue full'))
        book=MaintenanceBook(NS(submit=Mock(return_value=future)))
        book.record(PhysicalResult('F01','fan','PASSED_USER','observed'),2,self.state())
        self.assertEqual(book.errors,1)
        self.assertFalse(book._record_futures)

    def test_late_disk_error_is_consumed_once_and_pending_writes_are_bounded(self):
        futures=[]
        def submit(*args,**kwargs):
            f=Future();futures.append(f);return f
        book=MaintenanceBook(NS(submit=submit))
        for _ in range(9):
            book.record(PhysicalResult('F01','fan','PASSED_USER','observed'),2,self.state())
        self.assertEqual(len(futures),8)
        self.assertEqual(book.errors,1)
        futures[0].set_exception(OSError('disk full'))
        self.assertTrue(book.poll_records())
        self.assertFalse(book.poll_records())
        self.assertEqual(book.errors,2)


class F12RecordingTests(unittest.TestCase):
    def test_terminal_stop_results_reach_history_and_assessment_once(self):
        for status in ('PASSED_USER','FAILED_USER'):
            with self.subTest(status=status):
                printer = object.__new__(PrinterData)
                row = NS(method=2)
                result = PhysicalResult('F12','fan',status,'finished',True,
                    (('pwm_lower',10),('pwm_upper',12)))
                printer.state = NS()
                printer.maintenance_book = Mock()
                printer.maintenance_assessment = Mock()
                printer.maintenance_pulse = NS(_row=row,
                    f12_confirm_stopped=Mock(return_value=(result,'finished')))
                self.assertEqual(printer.confirm_maintenance_f12_stopped(),(result,'finished'))
                printer.maintenance_book.record.assert_called_once_with(result,2,printer.state,row)
                printer.maintenance_assessment.ingest.assert_called_once_with(result,2,printer.state)

    def test_nonterminal_round_acceptance_is_not_recorded(self):
        printer = object.__new__(PrinterData)
        printer._record_maintenance_result = Mock()
        for value in (True,False,None):
            printer.maintenance_pulse = NS(_row=NS(method=2),
                f12_confirm_stopped=Mock(return_value=(value,'round')))
            self.assertEqual(printer.confirm_maintenance_f12_stopped(),(value,'round'))
        printer._record_maintenance_result.assert_not_called()


class TraceTransportTests(unittest.TestCase):
    def test_pulse_json_keyword_survives_recording_proxy(self):
        future = Future()
        target = NS(subscription=NS(),postREST=Mock(return_value=future))
        trace = NS(context=lambda:{},emit=Mock(),dropped=0)
        proxy = PrinterProxy(target,trace)
        payload = {'script':'M106 S191\nG4 P950\nM106 S0'}
        guard = lambda:True
        result = proxy.postREST('/printer/gcode/script',json=payload,
            report_error=False,dispatch_guard=guard,request_timeout=9.)
        self.assertIs(result,future)
        target.postREST.assert_called_once_with('/printer/gcode/script',payload,
            report_error=False,dispatch_guard=guard,request_timeout=9.)
        future.set_result('ok')
        self.assertEqual(trace.dropped,0)


class RuntimeSafetyTests(unittest.TestCase):
    def test_old_workflow_stop_cannot_dispatch_into_a_new_epoch(self):
        life = {'epoch':12,'state':'ready'}
        subscription = NS(request=Mock(return_value=Future()),lifecycle=lambda:life)
        owner = FirmwareWorkflow(NS(subscription=subscription), None, None)
        owner._row = NS(epoch=12)
        owner._shutdown('workflow_lifecycle_changed')
        guard = subscription.request.call_args.kwargs['guard']
        self.assertTrue(guard())
        life['epoch'] = 13
        self.assertFalse(guard())

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
