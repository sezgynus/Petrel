"""Sensor observation, persistence and reminder integration regressions."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from maintenance_sensor_usage import BASIS, SensorMetric, SensorUsage, sensor_metrics
from maintenance_usage import usage_metrics
from maintenance_records import MaintenanceBook, read_json, write_json
from maintenance_assessment_store import ServicePolicy, AssessmentStore
from maintenance_ui_records import request
from maintenance_care_view import care_items
from maintenance_experience import Choice
from test_maintenance_ui_services import DeferredWorker

SENSOR = 'filament_switch_sensor arbitrary_name'


def state(value=False, *, ready=True, epoch=1, settings=None):
    return NS(ready=ready, epoch=epoch, settings=CONFIG if settings is None else settings,
              objects=(SENSOR,), status={SENSOR: {'filament_detected': value}})


CONFIG = {}


class SensorSourceTests(unittest.TestCase):
    def test_documented_sources_and_physical_endstops_only(self):
        objects = (SENSOR, 'filament_motion_sensor motion', 'gcode_button door',
                   'probe', 'query_endstops', 'output_pin misleading_switch')
        settings = {'stepper_x': {'endstop_pin': '^PA1'},
                    'stepper_y': {'endstop_pin': 'tmc2209_stepper_y:virtual_endstop'}}
        metrics = sensor_metrics(objects, settings)
        self.assertEqual({m.device for m in metrics},
                         {SENSOR, 'filament_motion_sensor motion', 'gcode_button door',
                          'probe', 'endstop stepper_x'})
        endstop = next(m for m in metrics if m.device == 'endstop stepper_x')
        self.assertEqual(endstop.source, 'query_endstops')
        for raw, expected in (({'stepper_x': 1}, True), ({'x': False}, False),
                              ({'stepper_x': 0, 'x': 1}, None),
                              ({'stepper_x': 'TRIGGERED'}, None), ({}, None)):
            self.assertIs(endstop.active({'query_endstops': {'last_query': raw}}), expected)
        self.assertEqual(sensor_metrics((), settings), ())

    def test_sensor_values_fail_closed_and_names_do_not_define_roles(self):
        metric = SensorMetric(SENSOR, SENSOR, 'filament_detected')
        for value in (None, 0, 1, 'true', float('nan'), {}, []):
            self.assertIsNone(metric.active({SENSOR: {'filament_detected': value}}))
        self.assertIs(metric.active({SENSOR: {'filament_detected': False}}), False)
        button = SensorMetric('gcode_button door', 'gcode_button door', 'state')
        self.assertIs(button.active({'gcode_button door': {'state': 'PRESSED'}}), True)
        self.assertIs(button.active({'gcode_button door': {'state': 'RELEASED'}}), False)
        self.assertIsNone(button.active({'gcode_button door': {'state': 'unknown'}}))

    def test_ready_metric_contract_is_bounded_and_subscribes_source_not_ui_identity(self):
        metrics, omitted = usage_metrics((SENSOR, 'query_endstops'),
                                         {'stepper_x': {'endstop_pin': 'PA1'}})
        self.assertEqual({m.metric_id for m in metrics}, {BASIS})
        self.assertIn(('query_endstops', 'last_query'),
                      {(getattr(m, 'source', m.device), m.field) for m in metrics})
        metrics, omitted = usage_metrics(tuple('gcode_button b%03d' % i for i in range(100)))
        self.assertEqual(len(metrics), 64)
        self.assertEqual(omitted, 36)


class SensorSubscriptionTests(unittest.TestCase):
    def test_bootstrap_preserves_source_mapping_and_latest_sensor_states(self):
        from moonraker_subscription import MoonrakerSubscription
        from test_subscription import FakeSocket
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        sock = FakeSocket()
        sock.snapshot.update({SENSOR: {'filament_detected': False},
                              'gcode_button door': {'state': 'RELEASED'},
                              'query_endstops': {'last_query': {'stepper_x': False}}})
        sub._socket = sock
        sub._bootstrap()
        objects = next(r['params']['objects'] for r in sock.sent
                       if r['method'] == 'printer.objects.subscribe')
        self.assertEqual(objects[SENSOR], ['filament_detected'])
        self.assertEqual(objects['gcode_button door'], ['state'])
        sub._merge({SENSOR: {'filament_detected': True}}, 11)
        self.assertIs(sub.snapshot()['status'][SENSOR]['filament_detected'], True)
        sub._invalidate('offline')
        self.assertEqual(sub._usage_fields, {})


class SensorLedgerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.home = patch('maintenance_records.Path.home', return_value=Path(self.folder.name))
        self.home.start()
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.home.stop)

    def test_edges_not_initial_active_repeated_true_or_release_and_no_fake_on_hours(self):
        book = MaintenanceBook(DeferredWorker())
        for now, value in enumerate((True, True, False, True, True, False, True)):
            book.note(state(value), now)
        usage = book.service_counters()
        self.assertEqual(usage[BASIS], {SENSOR: 2})
        self.assertEqual(usage['sampled_on_s'], {})
        self.assertIn((SENSOR, BASIS), usage['available_metrics'])
        self.assertIn((SENSOR+'.'+BASIS, 2), book.read('S12'))
        self.assertEqual(usage['sensor_counter_id'], book.service_counters()['sensor_counter_id'])

    def test_gaps_missing_fields_disconnect_and_epoch_change_never_bridge(self):
        book = MaintenanceBook(DeferredWorker())
        book.note(state(False), 0)
        book.note(state(True), 3)   # gap
        book.note(state(False), 4)
        book.note(state(None), 5)   # invalid
        book.note(state(True), 6)
        book.note(state(False), 7)
        book.note(state(ready=False), 8)
        book.note(state(True), 9)
        book.note(state(False), 10)
        book.note(state(True, epoch=2), 11)
        book.note(state(False, epoch=2), 12)
        book.note(state(True, epoch=2), 13)
        self.assertEqual(book.service_counters()[BASIS][SENSOR], 1)
        book.note(state(ready=False), 14)
        self.assertNotIn((SENSOR, BASIS), book.service_counters()['available_metrics'])

    def test_failed_write_retry_restart_and_legacy_identity_are_preserved(self):
        write_json('maintenance-usage.json', dict(version=1, counter_id='b'*32,
                   sampled_on_s={'fan': 42.0}, sampled_print_s=100.0))
        book = MaintenanceBook(DeferredWorker())
        book.note(state(False), 0)
        book.note(state(True), 1)
        with patch('maintenance_records.write_json', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                book.service_counters()
        first = book.service_counters()
        self.assertEqual(first[BASIS][SENSOR], 1)
        self.assertEqual(first['counter_id'], 'b'*32)
        self.assertEqual(first['sampled_on_s']['fan'], 42.0)
        book = MaintenanceBook(DeferredWorker())
        book.note(state(True), 0)   # restart while active is not another event
        second = book.service_counters()
        self.assertEqual(second[BASIS][SENSOR], 1)
        self.assertEqual(first['sensor_counter_id'], second['sensor_counter_id'])

    def test_last_query_changes_are_observations_not_periodic_new_triggers(self):
        book = MaintenanceBook(DeferredWorker())
        settings = {'stepper_x': {'endstop_pin': '^PA1'}}
        raw = NS(ready=True, epoch=1, settings=settings,
                 objects=('query_endstops', 'probe'), status={})
        for now, value in enumerate((None, False, True, True, False, True)):
            raw.status = {'query_endstops': {'last_query': {} if value is None else {'stepper_x': value}},
                          'probe': {'last_query': value}}
            book.note(raw, now)
        counters = book.service_counters()
        self.assertEqual(counters[BASIS], {'probe': 2, 'endstop stepper_x': 2})
        self.assertEqual(counters['sampled_on_s'], {})

    def test_capacity_and_invalid_ledger_preserve_existing_data(self):
        write_json('maintenance-sensor-usage.json', dict(version=1, counter_id='c'*32,
                   counts={'gcode_button old%d' % i: i for i in range(128)}))
        book = MaintenanceBook(DeferredWorker())
        book.note(state(False), 0)
        usage = book.service_counters()
        self.assertEqual(len(usage[BASIS]), 128)
        self.assertNotIn((SENSOR, BASIS), usage['available_metrics'])
        self.assertIn((SENSOR, 'capacity'), book.sensors.tracking())
        before = read_json('maintenance-sensor-usage.json', {})
        before['counts']['gcode_button old0'] = -1
        write_json('maintenance-sensor-usage.json', before)
        with self.assertRaises(ValueError):
            book.service_counters()
        self.assertEqual(read_json('maintenance-sensor-usage.json', {})['counts']['gcode_button old0'], -1)

    def test_export_contains_sensor_counter_without_modifying_totals(self):
        book = MaintenanceBook(DeferredWorker())
        book.note(state(False), 0)
        book.note(state(True), 1)
        book.read('S20')
        report = read_json('maintenance-report.json', {})
        self.assertEqual(report[BASIS][SENSOR], 1)
        self.assertEqual(report['sensor_coverage'], 'observed_transitions_lower_bound')


class SensorReminderTests(unittest.TestCase):
    def test_count_policy_anchors_due_completion_pause_and_reload(self):
        with tempfile.TemporaryDirectory() as folder, patch('maintenance_ui_records.Path.home', return_value=Path(folder)):
            worker = DeferredWorker()
            policy = ServicePolicy('sensor', SENSOR, BASIS, 3, 'user')
            usage = {BASIS: {SENSOR: 10}, 'sensor_counter_id': 'a'*32,
                     'counter_id': 'b'*32, 'available_metrics': ((SENSOR, BASIS),)}
            def call(operation):
                f = request(worker, operation, policy=policy if operation != 'load' else None,
                            devices=(SENSOR,), usage_provider=lambda: usage)
                worker.run()
                return f.result()[0][0]
            task = call('save_policy')
            self.assertIsNone(task[1].get('timestamp'))
            self.assertEqual(task[2], 'unknown')
            usage[BASIS][SENSOR] = 12
            task = call('load')
            self.assertIn('2/3 triggers recorded', care_items((task,), (SENSOR,), 0)[0].detail)
            usage[BASIS][SENSOR] = 13
            self.assertEqual(call('load')[2], 'due')
            completed = call('complete')
            self.assertEqual(completed[1]['counter'], 13)
            self.assertEqual(completed[1]['counter_id'], 'a'*32)
            self.assertEqual(usage[BASIS][SENSOR], 13)
            usage['available_metrics'] = ()
            task = call('load')
            self.assertEqual(care_items((task,), (SENSOR,), 0)[0].detail, 'Tracking paused')
            usage['available_metrics'] = ((SENSOR, BASIS),)
            usage[BASIS][SENSOR] = 16
            self.assertEqual(call('load')[2], 'due')

    def test_ui_sensor_class_count_units_and_no_implicit_save(self):
        from test_capabilities import display, snapshot
        raw = snapshot(probe=True)
        view = display(raw)
        view._maintenance_init()
        view._maintenance_options = lambda: ((), ())
        self.assertIn(BASIS, view.pd.maintenance_service_bases('probe'))
        view._maintenance_dispatch(Choice('Probe', 'service_device', 'probe'))
        self.assertEqual(view._maintenance_context, ('probe', 'sensor'))
        choice = next(c for c in view._maintenance_screen().choices if c.value == ('probe', 'sensor', BASIS))
        view._maintenance_dispatch(choice)
        self.assertIn('30 observed activations', str(view._maintenance_screen()))
        view._maintenance_dispatch(Choice('Review', 'service_review'))
        self.assertEqual(view._maintenance_context.interval, 30)
        self.assertIn('30 observed activations', str(view._maintenance_screen()))
