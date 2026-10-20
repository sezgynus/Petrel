"""Observed sensor activations, never an exact physical switch lifetime.

Only a verified inactive -> active pair in one short READY interval counts.
Endstop/probe inputs are last-query results, not continuous GPIO observations.
No polling, G-code, movement, or Klipper configuration is introduced here.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
import re
import uuid

BASIS = 'observed_trigger_count'
MAX_COUNTERS = 128
MAX_COUNT = 2**53-1


@dataclass(frozen=True, slots=True)
class SensorMetric:
    device: str
    source: str
    field: str
    key: str = ''
    metric_id: str = BASIS
    unit: str = 'count'

    def active(self, status):
        raw = status.get(self.source)
        value = raw.get(self.field) if isinstance(raw, Mapping) else None
        if self.key:
            if not isinstance(value, Mapping):
                return None
            # Klipper normally registers full stepper names. Accept the
            # documented axis alias only when it does not contradict them.
            keys = (self.key, self.key[-1]) if self.key in (
                'stepper_x', 'stepper_y', 'stepper_z') else (self.key,)
            values = [value[k] for k in keys if k in value]
            if not values or any(type(v) not in (bool, int) or v not in (0, 1) for v in values):
                return None
            return bool(values[0]) if all(v == values[0] for v in values) else None
        if self.field == 'state':
            return {'PRESSED': True, 'RELEASED': False}.get(value) if isinstance(value, str) else None
        return value if type(value) is bool else None


def sensor_metrics(objects, settings):
    """Discover documented sources once at READY; config alone is not readback."""
    names = set(objects)
    result = []
    for name in sorted(n for n in names if isinstance(n, str)):
        if name.startswith(('filament_switch_sensor ', 'filament_motion_sensor ')):
            result.append(SensorMetric(name, name, 'filament_detected'))
        elif name.startswith('gcode_button '):
            result.append(SensorMetric(name, name, 'state'))
        elif name == 'probe':
            result.append(SensorMetric(name, name, 'last_query'))
    if 'query_endstops' in names and isinstance(settings, Mapping):
        from maintenance_care import inventory
        devices, _ = inventory((), settings)
        for device in devices:
            if device.startswith('endstop '):
                result.append(SensorMetric(device, 'query_endstops', 'last_query', device[8:]))
    return tuple(result)


def _count(value):
    return type(value) is int and 0 <= value <= MAX_COUNT


class SensorUsage:
    """Bounded owner observations; worker-only atomic persistence and retry."""
    def __init__(self):
        self.lock = Lock()
        self.previous = None
        self.pending = {}
        self.seen = set()
        self.available = ()
        self.rejected = set()

    def note(self, state, metrics, now):
        current = {}
        if state.ready:
            for metric in metrics:
                if metric.metric_id == BASIS:
                    value = metric.active(state.status)
                    if value is not None:
                        current[metric.device] = value
        with self.lock:
            key = (state.epoch, id(state.settings))
            previous = self.previous
            if previous is None or previous[0] != key:
                self.rejected.clear()
            continuous = (previous is not None and previous[0] == key
                          and 0 < now-previous[1] <= 2)
            for device, active in current.items():
                if device in self.rejected:
                    continue
                if device not in self.seen:
                    if len(self.seen) >= MAX_COUNTERS:
                        self.rejected.add(device)
                        continue
                    self.seen.add(device)
                    self.pending.setdefault(device, 0)
                if continuous and previous[2].get(device) is False and active:
                    self.pending[device] = self.pending.get(device, 0)+1
            self.available = tuple(d for d in current if d not in self.rejected)
            self.previous = (key, now, current) if state.ready else None

    def counters(self):
        # The MaintenanceBook disk lock serializes all persistence calls.
        from maintenance_records import read_json, write_json
        with self.lock:
            pending, self.pending = self.pending, {}
        try:
            data = read_json('maintenance-sensor-usage.json', {})
            if not data and not pending:
                return {BASIS: {}, 'sensor_counter_id': None, 'sensor_available': ()}
            if not data:
                data = dict(version=1, counter_id=uuid.uuid4().hex, counts={})
            counts = data.get('counts')
            if (not isinstance(data.get('counter_id'), str)
                    or not re.fullmatch('[a-f0-9]{32}', data['counter_id'])
                    or not isinstance(counts, dict) or len(counts) > MAX_COUNTERS
                    or any(not isinstance(k, str) or not 0 < len(k.encode('utf-8')) <= 96
                           or not _count(v) for k, v in counts.items())):
                raise ValueError('invalid_sensor_usage')
            changed = False
            rejected = set()
            for device, value in sorted(pending.items()):
                if device not in counts and len(counts) >= MAX_COUNTERS:
                    rejected.add(device)
                    continue
                total = counts.get(device, 0)+value
                if not _count(total):
                    raise ValueError('sensor_usage_overflow')
                if device not in counts or value:
                    counts[device] = total
                    changed = True
            if changed:
                write_json('maintenance-sensor-usage.json', data)
        except Exception:
            with self.lock:
                for device, value in pending.items():
                    self.pending[device] = self.pending.get(device, 0)+value
            raise
        with self.lock:
            self.rejected.update(rejected)
            available = tuple(d for d in self.available if d in counts and d not in self.rejected)
        return {BASIS: dict(counts), 'sensor_counter_id': data['counter_id'],
                'sensor_available': available}

    def tracking(self):
        with self.lock:
            return tuple((d, 'capacity' if d in self.rejected else
                          'observed' if d in self.available else 'paused')
                         for d in sorted(self.seen | self.rejected))
