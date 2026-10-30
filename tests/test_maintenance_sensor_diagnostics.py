"""Read-only, on-demand sensor reports and Graphite navigation contracts."""
from concurrent.futures import Future
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from petrel.features.maintenance.domains.sensors.diagnostics import read, devices
from petrel.features.maintenance.ui.experience import Choice
from test_capabilities import display, snapshot

SENSOR = 'filament_switch_sensor arbitrary_name'


def state(objects=(SENSOR,), settings=None, ready=True):
    return NS(ready=ready, objects=objects,
              settings={SENSOR: {'switch_pin': 'PA1'}} if settings is None else settings)


class SensorReadingTests(unittest.TestCase):
    def test_filament_data_and_safe_encoded_one_object_request(self):
        name = 'filament_switch_sensor room sensor'
        client = Mock()
        client.get.return_value = {'result': {'status': {name: {
            'enabled': True, 'filament_detected': False, 'unexpected': 'private'}}}}
        result = read(client, state((name,), {name: {}}), name)
        query = parse_qs(urlsplit(client.get.call_args.args[0]).query)
        self.assertEqual(set(query), {name})
        self.assertIn('filament_detected', query[name][0])
        self.assertEqual(result.facts, (('Sensor enabled', 'Yes'), ('Filament detected', 'No')))
        self.assertTrue(result.configured)
        self.assertTrue(result.listed)
        self.assertNotIn('private', str(result))
        client.post.assert_not_called()

    def test_endstop_and_probe_remain_last_query_not_live_readings(self):
        cases = (
            ('endstop stepper_x', 'query_endstops',
             {'stepper_x': {'endstop_pin': 'PA1'}}, {'last_query': {'stepper_x': True}}),
            ('probe', 'probe', {'bltouch': {}}, {'last_query': False}),
        )
        for device, source, settings, raw in cases:
            with self.subTest(device=device):
                client = Mock()
                client.get.return_value = {'result': {'status': {source: raw}}}
                result = read(client, state((source,), settings), device)
                self.assertTrue(result.configured)
                self.assertTrue(result.listed)
                self.assertIn('Last query', str(result.facts))
                self.assertIn('not a continuous live pin reading', str(result.notes))
                self.assertTrue(client.get.call_args.args[0].startswith('/printer/objects/query?'))
                self.assertNotIn('/printer/query_endstops/status', client.get.call_args.args[0])
                client.post.assert_not_called()

    def test_configuration_object_and_read_availability_are_separate(self):
        client = Mock()
        result = read(client, state((), {'bltouch': {}}), 'bltouch')
        self.assertTrue(result.configured)
        self.assertFalse(result.listed)
        self.assertFalse(result.facts)
        client.get.assert_not_called()
        result = read(client, state(ready=False), SENSOR)
        self.assertIn('Klipper unavailable', str(result.notes))
        client.get.assert_not_called()
        client.get.side_effect = OSError('unavailable')
        result = read(client, state(), SENSOR)
        self.assertTrue(result.listed)
        self.assertFalse(result.facts)
        self.assertIn('Refresh to retry', str(result.notes))

    def test_numeric_fields_signed_temperatures_and_invalid_values(self):
        name = 'temperature_sensor arbitrary'
        client = Mock()
        client.get.return_value = {'result': {'status': {name: {
            'temperature': -2.5, 'measured_min_temp': -4.0,
            'measured_max_temp': float('nan'), 'humidity': True,
            'pressure': float('inf'), 'Raw': 10**1000}}}}
        result = read(client, state((name,), {name: {}}), name)
        self.assertIn(('Temperature', '-2.5 C'), result.facts)
        self.assertIn(('Minimum since restart', '-4 C'), result.facts)
        self.assertEqual(len(result.facts), 2)

    def test_many_configured_sensors_are_not_filtered_by_test_permissions(self):
        names = tuple('temperature_sensor s%d' % i for i in range(256))
        self.assertEqual(devices(NS(care_devices=names+('fan', 'servo latch'))), names)

    def test_invalid_endstop_aliases_and_source_without_supported_fields(self):
        client = Mock()
        client.get.return_value = {'result': {'status': {'query_endstops': {
            'last_query': {'stepper_x': False, 'x': True}}}}}
        result = read(client, state(('query_endstops',),
                      {'stepper_x': {'endstop_pin': 'PA1'}}), 'endstop stepper_x')
        self.assertEqual(result.facts, ())
        self.assertIn('No supported reading', str(result.notes))


class SensorDiagnosticUITests(unittest.TestCase):
    def view(self):
        raw = snapshot(probe=True)
        raw['objects'].append(SENSOR)
        raw['settings'][SENSOR] = {'switch_pin': 'PA1'}
        view = display(raw)
        view.checkkey = view.MaintenanceMenu
        view._maintenance_init()
        view._maintenance_options = lambda: ((), ())
        view._advance_maintenance_operations = Mock()
        return view

    def test_entry_read_report_refresh_back_and_no_hardware_action(self):
        view = self.view()
        view._maintenance_page = 'diagnostic_groups'
        choice = next(c for c in view._maintenance_screen().choices if c.value == 'sensor_devices')
        view._maintenance_dispatch(choice)
        self.assertEqual(view._maintenance_page, 'sensor_devices')
        self.assertIn(SENSOR, {c.value for c in view._maintenance_screen().choices})
        future = Future()
        view.pd.maintenance_sensor_diagnostic = Mock(return_value=future)
        view._maintenance_dispatch(Choice('Sensor', 'sensor_read', SENSOR))
        self.assertEqual(view._maintenance_page, 'sensor_wait')
        client = Mock()
        client.get.return_value = {'result': {'status': {SENSOR: {
            'filament_detected': True, 'enabled': True}}}}
        reading = read(client, state(), SENSOR)
        future.set_result(reading)
        view._poll_maintenance_ui()
        self.assertEqual(view._maintenance_page, 'sensor_report')
        screen = view._maintenance_screen()
        self.assertEqual(screen.kind, 'report')
        self.assertIn('Filament detected', str(screen.sections))
        view._maintenance_dispatch(next(c for c in screen.choices if c.action == 'sensor_refresh'))
        # Refresh replaces the report in place and keeps the device list as Back's parent.
        view._maintenance_dispatch(Choice('Back', 'back'))
        self.assertEqual(view._maintenance_page, 'sensor_devices')
        view.pd.sendGCode.assert_not_called()

    def test_late_result_after_back_does_not_redirect(self):
        view = self.view()
        view._maintenance_page = 'sensor_devices'
        future = Future()
        view.pd.maintenance_sensor_diagnostic = Mock(return_value=future)
        view._maintenance_dispatch(Choice('Sensor', 'sensor_read', SENSOR))
        view._maintenance_dispatch(Choice('Back', 'back'))
        future.set_result(NS(device=SENSOR))
        view._poll_maintenance_ui()
        self.assertEqual(view._maintenance_page, 'sensor_devices')

    def test_epoch_change_rejects_old_reading(self):
        view = self.view()
        future = Future()
        view.pd.maintenance_sensor_diagnostic = Mock(return_value=future)
        view._maintenance_dispatch(Choice('Sensor', 'sensor_read', SENSOR))
        view._maintenance_sensor_identity = ('old', 'epoch')
        future.set_result(NS(device=SENSOR))
        view._poll_maintenance_ui()
        self.assertEqual(view._maintenance_page, 'notice')
        self.assertIn('changed', str(view._maintenance_screen()))

    def test_repeat_report_draw_uses_existing_partial_render_cache(self):
        view = self.view()
        client = Mock()
        client.get.return_value = {'result': {'status': {SENSOR: {'filament_detected': True}}}}
        view._maintenance_page = 'sensor_report'
        view._maintenance_context = read(client, state(), SENSOR)
        view.Draw_Maintenance_Menu()
        view.lcd.reset_mock()
        view.Draw_Maintenance_Menu()
        view.lcd.draw_rectangle.assert_not_called()
        view.lcd.draw_string.assert_not_called()
