"""Device-specific thermal information: never physical PASS."""
import unittest
from petrel.features.maintenance.execution.executor import _read_fields, read_only_adapters
from petrel.features.maintenance.discovery.discovery import INFORMATION

class ThermalReadTests(unittest.TestCase):
    def test_target_and_eventtime_are_required(self):
        reply = {'result': {'eventtime': 10., 'status': {
            'temperature_sensor room': {'temperature': 24.5},
            'extruder': {'power': .25}}}}
        self.assertEqual(_read_fields('H14', reply, 'temperature_sensor room'),
                         (('klipper_eventtime_s', 10.), ('temperature', 24.5)))
        self.assertEqual(_read_fields('H11', reply, 'extruder')[-1], ('power', .25))
        self.assertEqual(_read_fields('H14', reply, 'missing'), ())
        del reply['result']['eventtime']
        self.assertEqual(_read_fields('H11', reply, 'extruder'), ())

    def test_malformed_and_nonfinite_values_are_not_evidence(self):
        for value in (True, float('nan'), float('inf'), -1, 1.1):
            reply = {'result': {'eventtime': 1., 'status': {'extruder': {'power': value}}}}
            self.assertEqual(_read_fields('H11', reply, 'extruder'), ())

    def test_environment_is_bounded_and_no_temperature_is_invented(self):
        reply = {'result': {'eventtime': 1., 'status': {'sensor': {
            'humidity': 40., 'pressure': 1010., 'secret': 'private'}}}}
        self.assertEqual(len(_read_fields('H16', reply, 'sensor')), 3)
        self.assertEqual(_read_fields('H14', reply, 'sensor'), ())

    def test_registrations_are_information_only(self):
        entries = {r.feature_id: r for r in read_only_adapters()}
        for feature in ('H11', 'H14', 'H16'):
            self.assertEqual(entries[feature].method, INFORMATION)

    def test_ui_keeps_device_optional_for_legacy_global_rows(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from test_capabilities import display,snapshot
        from petrel.features.maintenance.ui.experience import Choice
        d=display(snapshot());d._maintenance_init()
        row=SimpleNamespace(feature_id='S01')
        d.pd.start_maintenance_read=Mock(return_value=(True,'queued'))
        d._maintenance_dispatch(Choice('Host','read',row))
        d.pd.start_maintenance_read.assert_called_once_with('S01')
