"""Klipper event-total ledger and read-only legacy sampled sensor history.

SensorMetric is a status decoder for diagnostics only. Counting happens in the
existing Klipper extra; Petrel's read frequency never determines event counts.
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



EVENT_BASIS = 'trigger_count'
KINDS = frozenset(('switch_activation', 'encoder_rising_edge', 'homing_contact'))
MAX_SESSIONS = 8


def _count(value):
    return type(value) is int and 0 <= value <= MAX_COUNT


def event_sample(state):
    from petrel.features.maintenance.records.travel import OBJECT, installed
    raw = state.status.get(OBJECT) if state.ready and installed(state) else None
    if not isinstance(raw, Mapping) or type(raw.get('sensor_schema')) is not int or raw.get('sensor_schema') != 1:
        return None
    session, counts, kinds = raw.get('session_id'), raw.get('sensor_counts'), raw.get('sensor_kinds')
    disabled = raw.get('sensor_disabled', ())
    if (not isinstance(session, str) or not re.fullmatch('[a-f0-9]{32}', session)
            or raw.get('sensor_state') != 'tracking'
            or not isinstance(counts, Mapping) or len(counts) > 64
            or not isinstance(kinds, Mapping) or set(kinds) != set(counts)
            or not isinstance(disabled, (tuple, list)) or len(disabled) > 64
            or any(not isinstance(d, str) or d not in counts for d in disabled)
            or any(not isinstance(d, str) or not 0 < len(d.encode('utf-8')) <= 96
                   or not _count(v) or not isinstance(kinds[d], str) or kinds[d] not in KINDS for d, v in counts.items())):
        return None
    return session, dict(counts), dict(kinds), tuple(disabled)


class SensorUsage:
    """Read-only compatibility: sampled histories and their identities survive."""
    def counters(self):
        from petrel.features.maintenance.records.book import read_json
        data = read_json('maintenance-sensor-usage.json', {})
        if not data:
            return {BASIS: {}, 'sensor_counter_id': None, 'sensor_available': ()}
        counts = data.get('counts')
        if (not isinstance(data.get('counter_id'), str)
                or not re.fullmatch('[a-f0-9]{32}', data['counter_id'])
                or not isinstance(counts, dict) or len(counts) > MAX_COUNTERS
                or any(not isinstance(k, str) or not 0 < len(k.encode('utf-8')) <= 96
                       or not _count(v) for k, v in counts.items())):
            raise ValueError('invalid_sensor_usage')
        return {BASIS: dict(counts), 'sensor_counter_id': data['counter_id'],
                'sensor_available': ()}

    def tracking(self):
        return ()


class SensorEventLedger:
    """Existing worker persists cumulative totals and session checkpoints atomically."""
    def __init__(self):
        from collections import OrderedDict
        self.lock = Lock()
        self.pending = OrderedDict()
        self.available = ()
        self.rejected = set()
        self.kinds = {}

    def note(self, state):
        sample = event_sample(state)
        with self.lock:
            self.available = ()
            if sample is None:
                return
            session, counts, kinds, disabled = sample
            self.pending[session] = counts
            self.pending.move_to_end(session)
            if len(self.pending) > MAX_SESSIONS:
                self.pending.popitem(last=False)
            self.kinds = kinds
            self.available = tuple(d for d in counts if d not in disabled and d not in self.rejected)

    def counters(self):
        from petrel.features.maintenance.records.book import read_json, write_json, _encode
        with self.lock:
            pending = tuple((s, dict(v)) for s, v in self.pending.items())
            available = self.available
        data = read_json('maintenance-sensor-events.json', {})
        if not data and not pending:
            return {EVENT_BASIS: {}, 'event_counter_id': None, 'event_available': ()}
        if not data:
            data = dict(version=1, counter_id=uuid.uuid4().hex,
                        devices=[], totals=[], checkpoints={})
        names, totals, checkpoints = data.get('devices'), data.get('totals'), data.get('checkpoints')
        if (not isinstance(data.get('counter_id'), str)
                or not re.fullmatch('[a-f0-9]{32}', data['counter_id'])
                or not isinstance(names, list) or len(names) > MAX_COUNTERS
                or any(not isinstance(d, str) or not 0 < len(d.encode('utf-8')) <= 96 for d in names)
                or len(set(names)) != len(names) or not isinstance(totals, list)
                or len(totals) != len(names) or not all(_count(n) for n in totals)
                or not isinstance(checkpoints, dict) or len(checkpoints) > MAX_SESSIONS
                or any(not isinstance(s, str) or not re.fullmatch('[a-f0-9]{32}', s)
                       or not isinstance(v, list) or len(v) > len(names)
                       or any(n is not None and not _count(n) for n in v)
                       for s, v in checkpoints.items())):
            raise ValueError('invalid_sensor_event_ledger')
        indices = {d: i for i, d in enumerate(names)}
        rejected = set()
        changed = False
        for session, counts in pending:
            previous = checkpoints.get(session, [])
            current = list(previous)
            for device, count in sorted(counts.items()):
                if device not in indices:
                    # Reserve room for 8 checkpoint vectors at maximum counter
                    # width; long escaped names cannot make persistence unbounded.
                    if len(names) >= MAX_COUNTERS or len(_encode(names+[device]).encode('utf-8')) > 32000:
                        rejected.add(device)
                        continue
                    indices[device] = len(names)
                    names.append(device)
                    totals.append(0)
                    changed = True
                index = indices[device]
                if len(current) <= index:
                    current.extend([None]*(index+1-len(current)))
                old = current[index] if current[index] is not None else 0
                if count < old:
                    raise ValueError('sensor_event_counter_regressed')
                value = totals[index]+count-old
                if not _count(value):
                    raise ValueError('sensor_event_total_overflow')
                if current[index] != count:
                    totals[index] = value
                    current[index] = count
                    changed = True
            if current != previous or session not in checkpoints:
                checkpoints[session] = current
                changed = True
            while len(checkpoints) > MAX_SESSIONS:
                del checkpoints[next(iter(checkpoints))]
        if changed:
            write_json('maintenance-sensor-events.json', data)
        # Pending snapshots stay available on write failure, and newer owner
        # observations are never removed by a worker finishing an older flush.
        with self.lock:
            for session, counts in pending:
                if self.pending.get(session) == counts:
                    self.pending.pop(session, None)
            self.rejected.update(rejected)
            available = tuple(d for d in self.available if d in indices and d not in self.rejected)
        return {EVENT_BASIS: dict(zip(names, totals)), 'event_counter_id': data['counter_id'],
                'event_available': available}
