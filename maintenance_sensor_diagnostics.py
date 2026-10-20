"""Read-only sensor reports from existing Moonraker object-query contracts.

No pin polling, movement, probing, macros, config writes or per-sensor timers.
Configuration, object presence and the meaning of each reading stay distinct.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from urllib.parse import urlencode
from maintenance_care import family
from maintenance_sensor_usage import SensorMetric

FIELDS = ('enabled', 'filament_detected', 'state', 'last_query',
          'temperature', 'measured_min_temp', 'measured_max_temp',
          'humidity', 'pressure', 'gas', 'is_active', 'Diameter', 'Raw',
          'flow_compensation_enabled', 'is_calibrated', 'force_g',
          'min_force_g', 'max_force_g', 'errors', 'overflows', 'sample_rate')
LABELS = {
    'enabled': 'Sensor enabled', 'filament_detected': 'Filament detected',
    'state': 'Button state', 'last_query': 'Last query',
    'temperature': 'Temperature', 'measured_min_temp': 'Minimum since restart',
    'measured_max_temp': 'Maximum since restart', 'humidity': 'Humidity',
    'pressure': 'Pressure', 'gas': 'Gas resistance',
    'is_active': 'Measurement active', 'Diameter': 'Reported diameter',
    'Raw': 'Raw ADC reading', 'flow_compensation_enabled': 'Flow compensation',
    'is_calibrated': 'Calibrated', 'force_g': 'Force',
    'min_force_g': 'Minimum force', 'max_force_g': 'Maximum force',
    'errors': 'Sensor errors', 'overflows': 'Buffer overflows',
    'sample_rate': 'Samples per second'}
BOOL_FIELDS = frozenset(('enabled', 'filament_detected', 'is_active',
                         'flow_compensation_enabled', 'is_calibrated'))


def devices(snapshot):
    return tuple(d for d in getattr(snapshot, 'care_devices', ()) if family(d) == 'sensor')


def source_for(device, objects):
    if device.startswith('endstop '):
        return 'query_endstops'
    if device in ('bltouch', 'smart_effector') and 'probe' in objects:
        return 'probe'
    return device


@dataclass(frozen=True, slots=True)
class SensorReading:
    device: str
    source: str
    configured: bool
    listed: bool
    facts: tuple = ()
    notes: tuple = ()


def _value(field, value):
    if field in BOOL_FIELDS:
        return ('Yes' if value else 'No') if type(value) is bool else None
    if field == 'state':
        return value.capitalize() if isinstance(value, str) and value in ('PRESSED', 'RELEASED') else None
    if field == 'last_query':
        return ('Triggered' if value else 'Open') if type(value) is bool else None
    if type(value) not in (int, float):
        return None
    try:
        if not isfinite(value):
            return None
    except OverflowError:
        return None
    unit = (' C' if field in ('temperature', 'measured_min_temp', 'measured_max_temp') else
            ' %' if field == 'humidity' else ' mm' if field == 'Diameter' else
            ' g' if field in ('force_g', 'min_force_g', 'max_force_g') else '')
    return format(value, '.6g')+unit


def read(client, state, device):
    """Existing worker only. One bounded selection from one status object."""
    if family(device) != 'sensor':
        raise ValueError('not_a_sensor_device')
    source = source_for(device, state.objects)
    settings = state.settings
    configured = (device[8:] in settings if device.startswith('endstop ') else
                  device in settings or source == 'probe' and any(
                      n in settings for n in ('probe', 'bltouch', 'smart_effector')))
    listed = source in state.objects
    if not state.ready:
        return SensorReading(device, source, configured, listed,
                             notes=('Klipper unavailable; no current reading.',))
    if not listed:
        return SensorReading(device, source, configured, False,
                             notes=('No status object is exposed for this device.',))
    try:
        response = client.get('/printer/objects/query?'+urlencode({source: ','.join(FIELDS)}))
        result = response.get('result') if isinstance(response, Mapping) else None
        status = result.get('status') if isinstance(result, Mapping) else None
        raw = status.get(source) if isinstance(status, Mapping) else None
        if not isinstance(raw, Mapping):
            raise ValueError('sensor_status_missing')
    except (OSError, ValueError, RuntimeError):
        return SensorReading(device, source, configured, True,
                             notes=('Status read unavailable. Refresh to retry.',))
    facts = []
    if device.startswith('endstop '):
        value = SensorMetric(device, source, 'last_query', device[8:]).active({source: raw})
        if value is not None:
            facts.append(('Last query', 'Triggered' if value else 'Open'))
    else:
        for field in FIELDS:
            value = _value(field, raw.get(field))
            if value is not None:
                facts.append((LABELS[field], value))
    notes = []
    if source in ('probe', 'query_endstops') or 'last_query' in raw:
        notes.append('Last-query data; this is not a continuous live pin reading.')
        notes.append('Refresh reads stored status; it does not query or move the probe/endstop.')
    else:
        notes.append('Snapshot at read time; use Refresh for another reading.')
    if device.startswith('filament_motion_sensor '):
        notes.append('Detected state is not an encoder pulse counter.')
    if device.startswith('hall_filament_width_sensor'):
        notes.append('Diameter can be nominal while measurement is inactive.')
    if not facts:
        notes.append('No supported reading is reported by this status object.')
    return SensorReading(device, source, configured, True, tuple(facts), tuple(notes))
