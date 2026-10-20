"""Usage screens show current data and states, never migration/navigation prose."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from maintenance_records import MaintenanceBook, read_json, write_json
from maintenance_evidence_view import evidence_lines
from maintenance_experience import Screen, Choice
from maintenance_report import ReportSection
from maintenance_layout import draw_maintenance
from maintenance_travel import OBJECT
from test_maintenance_ui_services import DeferredWorker
import test_maintenance_ui_services as service_fixture


class CurrentUsagePresentationTests(unittest.TestCase):
    def test_legacy_history_is_preserved_and_exported_but_not_in_current_usage(self):
        with tempfile.TemporaryDirectory() as folder, patch('maintenance_records.Path.home', return_value=Path(folder)):
            device = 'filament_switch_sensor arbitrary'
            write_json('maintenance-sensor-usage.json',
                       dict(version=1, counter_id='a'*32, counts={device: 7}))
            path = Path(folder)/'.config/Petrel/maintenance-sensor-usage.json'
            before = path.read_bytes()
            book = MaintenanceBook(DeferredWorker())
            raw = NS(ready=True, epoch=1, settings={}, objects=(OBJECT,), status={OBJECT: dict(
                session_id='b'*32, state='tracking', x_mm=0., y_mm=0., z_mm=2347.,
                sensor_schema=1, sensor_state='tracking', sensor_counts={device: 4},
                sensor_kinds={device: 'switch_activation'}, sensor_disabled=())})
            book.note(raw, 0)
            fields = book.read('S12')
            self.assertFalse(any(k.endswith(('.observed_trigger_count', '.sensor_tracking')) for k, _ in fields))
            shown = str(evidence_lines('S12', fields))
            self.assertIn('4 events recorded', shown)
            self.assertIn((device+'.event_kind', 'switch_activation'), fields)
            self.assertNotIn('switch activations', shown)
            self.assertNotIn('legacy', shown.lower())
            self.assertNotIn('lower bound', shown.lower())
            self.assertNotIn('intervals', shown.lower())
            self.assertNotIn('Z travel travel', shown)
            self.assertEqual(path.read_bytes(), before)
            book.read('S20')
            report = read_json('maintenance-report.json', {})
            self.assertEqual(report['observed_trigger_count'][device], 7)
            self.assertEqual(report['trigger_count'][device], 4)

    def test_cached_old_fields_do_not_reintroduce_migration_explanations(self):
        fields = (('sensor_coverage', 'legacy_sampled_history_paused'),
                  ('sensor_event_coverage', 'klipper_callback_totals'),
                  ('coverage', 'sampled_lower_bound_not_lifetime'),
                  ('probe.observed_trigger_count', 9), ('probe.sensor_tracking', 'paused'),
                  ('axis_z.travel_mm', 2347.), ('travel_tracking', 'tracking'))
        shown = evidence_lines('S12', fields)
        self.assertIn('Z travel: 2.347 m', shown)
        self.assertNotIn('Axis travel: Tracking', shown)
        self.assertEqual(len(shown), 1)

    def test_usage_history_only_displays_amounts_not_event_kinds_or_recorder_states(self):
        raw = (
            ('endstop stepper_x.trigger_count', 4),
            ('endstop stepper_y.trigger_count', 4),
            ('filament_switch_sensor mmu_gate_sensor.trigger_count', 0),
            ('probe.trigger_count', 4),
            ('endstop stepper_x.event_kind', 'homing_contact'),
            ('endstop stepper_y.event_kind', 'homing_contact'),
            ('filament_switch_sensor mmu_gate_sensor.event_kind', 'switch_activation'),
            ('probe.event_kind', 'homing_contact'),
            ('probe.event_tracking', 'paused'),
            ('fan.tracking_state', 'capacity'),
            ('axis_z.travel_mm', 2347.),
            ('travel_tracking', 'tracking'),
            ('usage_slots_remaining', 115),
            ('usage_tracking_omitted', 2))
        shown = evidence_lines('S12', raw)
        merged = ' '.join(shown)
        self.assertEqual(len(shown), 5)
        self.assertEqual(merged.count('X axis endstop'), 1)
        self.assertIn('4 events recorded', merged)
        self.assertIn('Z travel: 2.347 m', merged)
        for metadata in ('homing/probing contacts', 'switch activations',
                         'Event tracking paused', 'Counter capacity reached',
                         'Counter slots free', 'Tracking capacity excluded',
                         'Axis travel: Tracking'):
            self.assertNotIn(metadata, merged)

    def test_scrollable_report_never_draws_encoder_navigation_footer(self):
        view = service_fixture.MaintenanceServiceUI().view()
        screen = Screen('Diagnostic data', choices=(Choice('Back', 'back'),),
                        kind='report', sections=(ReportSection(text=tuple('Reading %d' % i for i in range(30))),))
        draw_maintenance(view, screen)
        text = ' '.join(str(call.args[-1]) for call in view.lcd.draw_text.call_args_list)
        self.assertNotIn('Turn to', text)
        self.assertNotIn('press to select', text)
        self.assertTrue(view.lcd.draw_text.called)

    def test_editors_do_not_explain_encoder_navigation(self):
        view = service_fixture.MaintenanceServiceUI().view()
        view._maintenance_page = 'service_interval'
        view._maintenance_context = ('probe', 'sensor', 30, 'trigger_count')
        self.assertNotIn('Turn to', str(view._maintenance_screen()))
        view._maintenance_page = 'reference_limit'
        view._maintenance_context = (None, 20)
        self.assertNotIn('Turn to', str(view._maintenance_screen()))
