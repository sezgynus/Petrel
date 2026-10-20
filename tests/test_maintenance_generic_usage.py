"""CI regressions for passive metric contracts, inventory and durable usage."""
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace as NS
from maintenance_discovery import discover, NONE
from maintenance_usage import usage_metrics, MAX_TRACKED_METRICS


class UsageContracts(unittest.TestCase):
    def test_inventory_includes_readable_outputs_without_actuation_permission(self):
        names = ('fan', 'heater_fan any', 'controller_fan any', 'fan_generic any',
                 'temperature_fan any', 'extruder', 'extruder2', 'heater_bed',
                 'heater_generic any', 'output_pin arbitrary', 'pwm_cycle_time sound',
                 'pwm_tool spindle')
        state = NS(ready=True, epoch=1, objects=names, settings={}, status={})
        snap = discover(state)
        self.assertEqual({m.device for m in snap.usage_metrics}, set(names))
        self.assertEqual(snap.method('O03', 'output_pin arbitrary'), NONE)
        self.assertEqual(snap.usage_omitted, 0)
        self.assertTrue(all(m.unit == 's' and m.metric_id == 'sampled_on_s'
                            for m in snap.usage_metrics))
        with self.assertRaises(FrozenInstanceError):
            snap.usage_metrics[0].field = 'other'

    def test_unsupported_objects_and_config_only_pins_do_not_create_metrics(self):
        state = NS(ready=True, epoch=1, objects=('servo a', 'stepper_x',
            'gcode_button a', 'filament_switch_sensor a', 'temperature_sensor a'),
            settings={'output_pin absent': {'pin': 'PA1'}}, status={})
        self.assertEqual(discover(state).usage_metrics, ())
        state.ready = False
        self.assertEqual(discover(state).usage_metrics, ())

    def test_contract_survives_missing_initial_sample_but_validates_each_value(self):
        metric = usage_metrics(('output_pin arbitrary',))[0][0]
        for value in (None, True, False, '1', -1, float('nan'), float('inf')):
            self.assertIsNone(metric.active({metric.device: {'value': value}}))
        self.assertIsNone(metric.active({}))
        self.assertIsNone(metric.active({metric.device: []}))
        self.assertIs(metric.active({metric.device: {'value': 0}}), False)
        self.assertIs(metric.active({metric.device: {'value': .3}}), True)

    def test_stable_capacity_preserves_standard_counters_and_reports_excess(self):
        names = ['output_pin p%03d' % i for i in range(100)] + ['fan', 'extruder', 'heater_bed']
        first, omitted = usage_metrics(names)
        self.assertEqual((first, omitted), usage_metrics(reversed(names)))
        self.assertEqual(len(first), MAX_TRACKED_METRICS)
        self.assertEqual(omitted, len(names) - MAX_TRACKED_METRICS)
        self.assertTrue({'fan', 'extruder', 'heater_bed'} <= {m.device for m in first})
        self.assertEqual(usage_metrics(('output_pin ' + 'a'*100,))[0], ())


class UsageSampling(unittest.TestCase):
    def test_generic_outputs_gaps_epochs_and_invalid_values(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from maintenance_records import MaintenanceBook
        from test_maintenance_ui_services import DeferredWorker
        with tempfile.TemporaryDirectory() as folder, patch('maintenance_records.root', return_value=Path(folder)):
            book = MaintenanceBook(DeferredWorker())
            names = ('fan', 'extruder', 'output_pin arbitrary', 'pwm_cycle_time tone')
            state = NS(ready=True, epoch=1, objects=names, settings={}, status={
                n: {('speed' if n == 'fan' else 'power' if n == 'extruder' else 'value'): 1.}
                for n in names})
            for now in (0., 1., 2., 10.): book.note(state, now)
            counters = book.service_counters()
            self.assertEqual(set(counters['sampled_on_s'].values()), {2.})
            identity = counters['counter_id']
            state.status['output_pin arbitrary']['value'] = float('nan')
            book.note(state, 11.)
            state.status['output_pin arbitrary']['value'] = 1.
            book.note(state, 12.)
            book.note(state, 13.)
            self.assertEqual(book.service_counters()['sampled_on_s']['output_pin arbitrary'], 3.)
            state.epoch += 1
            book.note(state, 14.)
            book.note(state, 15.)
            final = book.service_counters()
            self.assertEqual(final['sampled_on_s']['fan'], 6.)
            self.assertEqual(final['counter_id'], identity)
            self.assertEqual(MaintenanceBook(DeferredWorker()).service_counters()['counter_id'], identity)

    def test_legacy_ledger_identity_and_pending_survive_write_failure(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from maintenance_records import MaintenanceBook, write_json, read_json
        from test_maintenance_ui_services import DeferredWorker
        with tempfile.TemporaryDirectory() as folder, patch('maintenance_records.root', return_value=Path(folder)):
            write_json('maintenance-usage.json', {'version': 1, 'sampled_on_s': {'fan': 123},
                'sampled_print_s': 456, 'counter_id': 'a'*32})
            book = MaintenanceBook(DeferredWorker())
            book._usage = {'fan': 2., 'output_pin arbitrary': 3.}
            with patch('maintenance_records.write_json', side_effect=OSError('disk')):
                with self.assertRaises(OSError): book.flush()
            self.assertEqual(book._usage['output_pin arbitrary'], 3.)
            book.flush()
            data = read_json('maintenance-usage.json', {})
            self.assertEqual(data['sampled_on_s'], {'fan': 125., 'output_pin arbitrary': 3.})
            self.assertEqual(data['sampled_print_s'], 456)
            self.assertEqual(data['counter_id'], 'a'*32)
            self.assertFalse(book._usage)


class UsageSubscriptions(unittest.TestCase):
    def test_bootstrap_and_optional_leases_preserve_usage_fields(self):
        from concurrent.futures import Future
        from unittest.mock import Mock
        from moonraker_subscription import MoonrakerSubscription
        from test_subscription import FakeSocket
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        sock = FakeSocket()
        sock.snapshot.update({'output_pin arbitrary': {'value': 1.},
            'output_pin case_light': {'value': .5},
            'heater_generic chamber': {'power': .4}, 'fan_generic aux': {'speed': .7}})
        sub._socket = sock
        sub._bootstrap()
        request = next(r for r in sock.sent if r['method'] == 'printer.objects.subscribe')
        objects = request['params']['objects']
        self.assertEqual(objects['output_pin arbitrary'], ['value'])
        self.assertEqual(objects['heater_generic chamber'], ['power'])
        self.assertEqual(objects['fan_generic aux'], ['speed'])
        self.assertEqual(sub.snapshot()['status']['output_pin case_light']['value'], .5)
        sub.request = Mock(side_effect=lambda *a, **k: Future())
        sub.set_case_light_tracking(True)
        sub.set_thermal_tracking(True)
        sub.set_case_light_tracking(False)
        sub.set_thermal_tracking(False)
        self.assertEqual(sub.request.call_args.args[1]['objects']['heater_generic chamber'], ['power'])
        self.assertIn('output_pin case_light', sub.snapshot()['status'])
        sub._merge({'heater_generic chamber': {'power': .8}}, 11)
        self.assertEqual(sub.snapshot()['status']['heater_generic chamber']['power'], .8)
        sub._invalidate('offline')
        self.assertEqual(sub._usage_fields, {})


class UsagePlannerAndReports(unittest.TestCase):
    def test_readable_output_offers_reminder_without_a_safe_physical_test(self):
        from test_capabilities import display, snapshot
        raw = snapshot()
        raw['objects'] += ['output_pin arbitrary']
        raw['settings']['output_pin arbitrary'] = {'pin': 'PA1'}
        raw['status']['output_pin arbitrary'] = {'value': 0}
        view = display(raw)
        view._maintenance_init()
        # This test isolates passive service inventory from physical adapters.
        view._maintenance_options = lambda: ((), ())
        self.assertIn('output_pin arbitrary', view.pd.maintenance_service_devices())
        self.assertIn('sampled_on_s', view.pd.maintenance_service_bases('output_pin arbitrary'))
        view._maintenance_page = 'service_devices'
        self.assertTrue(any(c.value == 'output_pin arbitrary' for c in view._maintenance_screen().choices))
        self.assertNotIn('sampled_on_s', view.pd.maintenance_service_bases('stepper_x'))

    def test_missing_live_reading_pauses_without_resetting_saved_anchor(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from maintenance_assessment_store import AssessmentStore, ServicePolicy
        from maintenance_ui_records import request
        from test_maintenance_ui_services import DeferredWorker
        device = 'output_pin arbitrary'
        policy = ServicePolicy('inspect_clean', device, 'sampled_on_s', 100, 'user')
        usage = {'counter_id': 'a'*32, 'sampled_on_s': {device: 100}, 'available_metrics': ()}
        with tempfile.TemporaryDirectory() as folder, patch('maintenance_ui_records.Path.home', return_value=Path(folder)):
            worker = DeferredWorker()
            def call(op):
                future = request(worker, op, policy=policy if op != 'load' else None,
                    devices=(device,), usage_provider=lambda: usage)
                worker.run()
                return future.result()[0][0]
            first = call('save_policy')
            store = AssessmentStore(Path(folder)/'.config/Petrel/maintenance-assessment.json')
            self.assertIsNone(store.tracking_start(policy))
            self.assertTrue(first[1]['_tracking_paused'])
            usage['available_metrics'] = ((device, 'sampled_on_s'),)
            self.assertEqual(call('load')[1]['_sampled_elapsed_s'], 0)
            usage['sampled_on_s'][device] = 150
            self.assertEqual(call('load')[1]['_sampled_elapsed_s'], 50)
            usage['available_metrics'] = ()
            self.assertTrue(call('load')[1]['_tracking_paused'])
            self.assertEqual(store.tracking_start(policy)['counter'], 100)
            usage['available_metrics'] = ((device, 'sampled_on_s'),)
            self.assertEqual(call('complete')[1]['counter'], 150)
            self.assertEqual(usage['sampled_on_s'][device], 150)

    def test_all_128_counters_reach_report_pages_without_name_truncation(self):
        from unittest.mock import Mock, patch
        from maintenance_records import MaintenanceBook
        from maintenance_evidence_view import evidence_lines
        from maintenance_report import report_pages, section_from_lines
        counters = {'output_pin component_%03d'%i: float(i) for i in range(128)}
        with patch('maintenance_records.read_json', return_value={'sampled_on_s': counters}):
            fields = MaintenanceBook.read(NS(flush=Mock()), 'S12')
        lines = evidence_lines('S12', fields)
        pages = report_pages(section_from_lines('', lines))
        for i in range(128):
            self.assertIn('component_%03d'%i, str(pages))
        self.assertTrue(all(sum(b[2] for b in p) <= 132 for p in pages))
        self.assertIn('Counter slots free: 0', lines)

    def test_supported_and_observed_are_distinct_and_disconnect_pauses(self):
        from maintenance_records import MaintenanceBook
        from test_maintenance_ui_services import DeferredWorker
        book = MaintenanceBook(DeferredWorker())
        state = NS(ready=True, epoch=1, objects=('output_pin any',), settings={}, status={})
        book.note(state, 0)
        self.assertEqual(book.usage_status(), (('output_pin any', 'starting'),))
        state.status['output_pin any'] = {'value': 0}
        book.note(state, 1)
        self.assertEqual(book.usage_status(), (('output_pin any', 'observed'),))
        state.ready = False
        book.note(state, 2)
        self.assertEqual(book.usage_status(), (('output_pin any', 'paused'),))
