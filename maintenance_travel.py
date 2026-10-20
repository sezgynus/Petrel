"""Tiny optional travel ledger; owner observes, existing worker persists.

Checkpoint and totals share one atomic file, preventing replay after Petrel
restart. Missing sessions/tails cannot be reconstructed: always a lower bound.
"""
from collections.abc import Mapping
from collections import OrderedDict
from threading import Lock
import os
import re
import uuid
from maintenance_usage import numeric

OBJECT = 'petrel_axis_travel'
AXES = ('axis_x', 'axis_y', 'axis_z')


def travel_device(device):
    """Existing UI axis names resolve to Cartesian counters, not motor odometry.

    Numbered motors and manual steppers are deliberately not aliases.
    Existing axis_* policies keep their original identity and anchor.
    """
    return 'axis_'+device[-1] if device in ('stepper_x','stepper_y','stepper_z') else device


def installed(state):
    return (os.environ.get('PETREL_AXIS_TRAVEL','1')!='0'
            and OBJECT in getattr(state,'objects',()))


class TravelLedger:
    def __init__(self):
        self.lock = Lock()
        self.latest = None
        self.pending = OrderedDict()
        self.available = False

    def note(self, state):
        raw = state.status.get(OBJECT, {}) if state.ready and installed(state) else {}
        valid = (isinstance(raw, Mapping) and raw.get('state') == 'tracking'
                 and isinstance(raw.get('session_id'), str)
                 and re.fullmatch('[a-f0-9]{32}', raw['session_id'])
                 and all(numeric(raw.get(k)) for k in ('x_mm','y_mm','z_mm')))
        with self.lock:
            self.available = bool(valid)
            if valid:
                self.latest = (raw['session_id'], tuple(raw[k] for k in ('x_mm','y_mm','z_mm')))
                self.pending[self.latest[0]] = self.latest[1]
                if len(self.pending)>8:
                    self.pending.popitem(last=False)

    def flush(self):
        # Imported here to keep the storage owner and its bounds unchanged.
        from maintenance_records import read_json, write_json
        with self.lock:
            pending, available = tuple(self.pending.items()), self.available
        data = read_json('maintenance-travel.json', {})
        if not data and not pending:
            return {}, False
        if not data:
            data = dict(version=1,counter_id=uuid.uuid4().hex,
                        totals=[0.,0.,0.],checkpoints={})
        if (data.get('version') != 1 or not isinstance(data.get('counter_id'),str)
                or not re.fullmatch('[a-f0-9]{32}',data['counter_id'])
                or not isinstance(data.get('totals'),list) or len(data['totals'])!=3
                or not all(numeric(v) for v in data['totals'])
                or not isinstance(data.get('checkpoints'),dict) or len(data['checkpoints'])>8
                or any(not isinstance(k,str) or not re.fullmatch('[a-f0-9]{32}',k)
                       or not isinstance(v,list) or len(v)!=3 or not all(numeric(x) for x in v)
                       for k,v in data['checkpoints'].items())):
            raise ValueError('invalid_travel_ledger')
        changed = False
        for session, values in pending:
            previous = data['checkpoints'].get(session,[0.,0.,0.])
            if any(a < b for a,b in zip(values,previous)):
                raise ValueError('travel_counter_regressed')
            if session not in data['checkpoints'] or list(values) != previous:
                data['totals'] = [a+b-c for a,b,c in zip(data['totals'],values,previous)]
                if not all(numeric(v) for v in data['totals']):
                    raise ValueError('invalid_travel_total')
                data['checkpoints'][session] = list(values)
                while len(data['checkpoints'])>8:
                    del data['checkpoints'][next(iter(data['checkpoints']))]
                changed = True
        if changed:
            write_json('maintenance-travel.json',data)
        with self.lock:
            for session,values in pending:
                if self.pending.get(session)==values:
                    self.pending.pop(session,None)
        return data, available

    def counters(self):
        data, available = self.flush()
        return dict(travel_mm=dict(zip(AXES,data.get('totals',()))),
                    travel_counter_id=data.get('counter_id'),
                    travel_available=available)
