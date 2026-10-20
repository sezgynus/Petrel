"""Event-total transport, durable continuity, legacy isolation and care policies."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from maintenance_sensor_usage import EVENT_BASIS, event_sample, SensorEventLedger
from maintenance_usage import usage_metrics
from maintenance_records import MaintenanceBook, read_json, write_json
from maintenance_assessment_store import ServicePolicy, AssessmentStore
from maintenance_ui_records import request
from maintenance_care_view import care_items
from maintenance_experience import Choice
from maintenance_travel import OBJECT
from test_maintenance_ui_services import DeferredWorker

SENSOR = 'filament_switch_sensor arbitrary_name'


def state(count=0, *, session='a'*32, ready=True, active=True):
    return NS(ready=ready, epoch=1, settings={}, objects=(OBJECT, SENSOR),
              status={OBJECT: dict(session_id=session, sensor_schema=1,
                  sensor_state='tracking' if active else 'paused',
                  sensor_counts={SENSOR: count}, sensor_kinds={SENSOR: 'switch_activation'},
                  sensor_disabled=(), x_mm=0., y_mm=0., z_mm=0., state='tracking')})


class EventLedgerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.home = patch('maintenance_records.Path.home', return_value=Path(self.folder.name))
        self.home.start()
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.home.stop)

    def test_large_reading_gaps_and_fast_source_events_are_not_lost(self):
        book = MaintenanceBook(DeferredWorker())
        book.note(state(0), 0)
        first = book.service_counters()
        book.note(state(1000), 100)  # no two-second filter applies to cumulative totals
        counters = book.service_counters()
        self.assertEqual(counters[EVENT_BASIS], {SENSOR: 1000})
        self.assertIn((SENSOR, EVENT_BASIS), counters['available_metrics'])
        self.assertEqual(first['event_counter_id'], counters['event_counter_id'])
        self.assertEqual(counters['sampled_on_s'], {})
        self.assertIn((SENSOR+'.trigger_count', 1000), book.read('S12'))

    def test_restart_reconnect_and_multiple_klipper_sessions_never_replay(self):
        book = MaintenanceBook(DeferredWorker())
        book.note(state(10), 0)
        first = book.service_counters()
        book = MaintenanceBook(DeferredWorker())
        book.note(state(10), 1)
        self.assertEqual(book.service_counters()[EVENT_BASIS][SENSOR], 10)
        book.note(state(20), 50)
        book.note(state(3, session='b'*32), 100)
        final = book.service_counters()
        self.assertEqual(final[EVENT_BASIS][SENSOR], 23)
        self.assertEqual(first['event_counter_id'], final['event_counter_id'])
        book.note(state(5, session='b'*32), 200)
        self.assertEqual(book.service_counters()[EVENT_BASIS][SENSOR], 25)

    def test_unavailable_option_off_and_old_extra_pause_without_zero(self):
        book = MaintenanceBook(DeferredWorker())
        book.note(state(12), 0)
        book.service_counters()
        for raw in (state(ready=False), state(active=False)):
            book.note(raw, 1)
            result = book.service_counters()
            self.assertEqual(result[EVENT_BASIS][SENSOR], 12)
            self.assertNotIn((SENSOR, EVENT_BASIS), result['available_metrics'])
        old = state()
        del old.status[OBJECT]['sensor_schema']
        book.note(old, 2)
        self.assertNotIn((SENSOR, EVENT_BASIS), book.service_counters()['available_metrics'])
        with patch.dict('os.environ', {'PETREL_AXIS_TRAVEL': '0'}):
            self.assertIsNone(event_sample(state(20)))
        book.note(state(20), 100)
        self.assertEqual(book.service_counters()[EVENT_BASIS][SENSOR], 20)

    def test_failed_atomic_write_retries_all_pending_counts_without_double_add(self):
        ledger = SensorEventLedger()
        ledger.note(state(10))
        with patch('maintenance_records.write_json', side_effect=OSError('full')):
            with self.assertRaises(OSError): ledger.counters()
        ledger.note(state(12))
        self.assertEqual(ledger.counters()[EVENT_BASIS][SENSOR], 12)
        self.assertEqual(ledger.counters()[EVENT_BASIS][SENSOR], 12)

    def test_invalid_or_regressed_source_does_not_reset_durable_totals(self):
        ledger = SensorEventLedger()
        ledger.note(state(10))
        ledger.counters()
        for value in (True, -1, 1.5, float('nan'), 2**54):
            raw = state(value)
            self.assertIsNone(event_sample(raw))
        raw = state()
        raw.status[OBJECT]['sensor_kinds'][SENSOR] = []
        self.assertIsNone(event_sample(raw))
        ledger.note(state(9))
        with self.assertRaisesRegex(ValueError, 'regressed'): ledger.counters()
        self.assertEqual(read_json('maintenance-sensor-events.json', {})['totals'], [10])

    def test_legacy_sampled_file_and_policies_are_never_merged_or_rewritten(self):
        write_json('maintenance-sensor-usage.json', dict(version=1,
                   counter_id='b'*32, counts={SENSOR: 7}))
        path = Path(self.folder.name)/'.config/Petrel/maintenance-sensor-usage.json'
        before = path.read_bytes()
        book = MaintenanceBook(DeferredWorker())
        book.note(state(100), 0)
        data = book.service_counters()
        self.assertEqual(data['observed_trigger_count'][SENSOR], 7)
        self.assertEqual(data[EVENT_BASIS][SENSOR], 100)
        self.assertNotEqual(data['event_counter_id'], data['sensor_counter_id'])
        self.assertNotIn((SENSOR, 'observed_trigger_count'), data['available_metrics'])
        self.assertEqual(path.read_bytes(), before)
        book.read('S20')
        report = read_json('maintenance-report.json', {})
        self.assertEqual(report[EVENT_BASIS][SENSOR], 100)
        self.assertEqual(report['observed_trigger_count'][SENSOR], 7)

    def test_sensor_states_are_no_longer_subscribed_or_counted_by_sampling(self):
        self.assertEqual(usage_metrics((SENSOR, 'probe', 'gcode_button door', 'query_endstops'))[0], ())
        book = MaintenanceBook(DeferredWorker())
        raw = state()
        raw.objects = (SENSOR,)
        for t, level in enumerate((False, True, False, True)):
            raw.status = {SENSOR: {'filament_detected': level}}
            book.note(raw, t)
        self.assertEqual(book.service_counters()[EVENT_BASIS], {})
        self.assertEqual(book.service_counters()['observed_trigger_count'], {})

    def test_long_names_and_many_sessions_stay_inside_record_byte_budget(self):
        ledger = SensorEventLedger()
        for session_index in range(8):
            raw = state()
            names = ['gcode_button '+('x'*65)+str(i) for i in range(64)]
            raw.status[OBJECT].update(session_id=('%032x' % (session_index+1)),
                sensor_counts={n: session_index+1 for n in names},
                sensor_kinds={n: 'switch_activation' for n in names})
            ledger.note(raw)
        data = ledger.counters()
        self.assertEqual(len(data[EVENT_BASIS]), 64)
        path = Path(self.folder.name)/'.config/Petrel/maintenance-sensor-events.json'
        self.assertLess(path.stat().st_size, 65536)
        self.assertTrue(all(v == 36 for v in data[EVENT_BASIS].values()))


class EventTransportTests(unittest.TestCase):
    def test_bootstrap_subscribes_extra_totals_without_per_sensor_status_sources(self):
        from moonraker_subscription import MoonrakerSubscription
        from test_subscription import FakeSocket
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        sock = FakeSocket()
        sock.snapshot[OBJECT] = state(10).status[OBJECT]
        sock.snapshot[SENSOR] = {'filament_detected': False}
        sub._socket = sock
        sub._bootstrap()
        objects = next(r['params']['objects'] for r in sock.sent
                       if r['method'] == 'printer.objects.subscribe')
        self.assertIn('sensor_counts', objects[OBJECT])
        self.assertIn('sensor_kinds', objects[OBJECT])
        self.assertNotIn(SENSOR, objects)
        sub._merge({OBJECT: {'sensor_counts': {SENSOR: 100}}}, 11)
        self.assertEqual(sub.snapshot()['status'][OBJECT]['sensor_counts'][SENSOR], 100)


class EventReminderTests(unittest.TestCase):
    def test_due_complete_pause_and_reconnect_keep_the_same_event_anchor(self):
        with tempfile.TemporaryDirectory() as folder, patch('maintenance_ui_records.Path.home', return_value=Path(folder)):
            worker = DeferredWorker()
            policy = ServicePolicy('sensor', SENSOR, EVENT_BASIS, 3, 'user')
            usage = {EVENT_BASIS: {SENSOR: 10}, 'event_counter_id': 'a'*32,
                     'counter_id': 'b'*32, 'available_metrics': ((SENSOR, EVENT_BASIS),)}
            def call(operation):
                f = request(worker, operation, policy=policy if operation != 'load' else None,
                            devices=(SENSOR,), usage_provider=lambda: usage)
                worker.run()
                return f.result()[0][0]
            self.assertIsNone(call('save_policy')[1].get('timestamp'))
            usage[EVENT_BASIS][SENSOR] = 12
            self.assertIn('2/3 events recorded', care_items((call('load'),), (SENSOR,), 0)[0].detail)
            usage[EVENT_BASIS][SENSOR] = 13
            self.assertEqual(call('load')[2], 'due')
            self.assertEqual(call('complete')[1]['counter_id'], 'a'*32)
            self.assertEqual(usage[EVENT_BASIS][SENSOR], 13)
            usage['available_metrics'] = ()
            self.assertEqual(care_items((call('load'),), (SENSOR,), 0)[0].detail, 'Tracking paused')
            usage['available_metrics'] = ((SENSOR, EVENT_BASIS),)
            usage[EVENT_BASIS][SENSOR] = 16
            self.assertEqual(call('load')[2], 'due')

    def test_only_loaded_schema_exposes_event_basis_and_review_uses_count_units(self):
        from test_capabilities import display, snapshot
        raw = snapshot(probe=True)
        raw['objects'].append(OBJECT)
        extra = state().status[OBJECT]
        extra['sensor_counts'] = {'probe': 0}
        extra['sensor_kinds'] = {'probe': 'homing_contact'}
        raw['status'][OBJECT] = extra
        view = display(raw)
        view._maintenance_init()
        view._maintenance_options = lambda: ((), ())
        self.assertIn(EVENT_BASIS, view.pd.maintenance_service_bases('probe'))
        self.assertNotIn(EVENT_BASIS, view.pd.maintenance_service_bases('missing'))
        view._maintenance_dispatch(Choice('Probe', 'service_device', 'probe'))
        self.assertEqual(view._maintenance_context, ('probe', 'sensor'))
        choice = next(c for c in view._maintenance_screen().choices if c.value == ('probe', 'sensor', EVENT_BASIS))
        view._maintenance_dispatch(choice)
        self.assertIn('2000 recorded events', str(view._maintenance_screen()))
        view._maintenance_dispatch(Choice('Review', 'service_review'))
        self.assertEqual(view._maintenance_context.interval, 2000)
        self.assertIn('2000 recorded events', str(view._maintenance_screen()))
