"""Explicit baseline and service policy storage; no assumed service intervals."""
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import math
from maintenance_assessment_model import Evidence, Measurement, comparable, _text

def numeric(value):
    return type(value) in (int,float) and math.isfinite(value) and value >= 0

@dataclass(frozen=True, slots=True)
class ServicePolicy:
    task_id: str
    device: str
    basis: str
    interval: float
    source: str

    def __post_init__(self):
        if (not all(_text(x) for x in (self.task_id,self.device,self.source))
                or self.basis not in ('calendar_s','print_s','sampled_on_s','travel_mm')
                or not numeric(self.interval) or self.interval <= 0):
            raise ValueError('invalid_service_policy')

def service_due(policy, *, now, last_at=None, current=None, previous=None,
                continuity=False, counter_id=None, previous_counter_id=None):
    """Missing/reset counters remain unknown. Sampled time can prove due only."""
    if policy.basis == 'calendar_s':
        if not numeric(now) or not numeric(last_at) or now < last_at:
            return 'unknown'
        return 'due' if now-last_at >= policy.interval else 'not_due'
    if (not continuity or not numeric(current) or not numeric(previous)
            or current < previous or not _text(counter_id)
            or counter_id != previous_counter_id):
        return 'unknown'
    if current-previous >= policy.interval:
        return 'due'
    return 'unknown' if policy.basis == 'sampled_on_s' else 'not_due'

def encode(evidence):
    return asdict(evidence)

def decode(data):
    d = dict(data)
    d['measurements'] = tuple(Measurement(**m) for m in d.get('measurements',()))
    d['conditions'] = tuple(tuple(p) for p in d.get('conditions',()))
    return Evidence(**d)

class AssessmentStore:
    """Small versioned atomic file; call on the existing worker, never draw path."""
    def __init__(self,path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return {'version':1,'baselines':{},'services':[]}
        if self.path.stat().st_size > 65536:
            raise ValueError('assessment_store_capacity')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if (type(data) is not dict or data.get('version') != 1
                or type(data.get('baselines')) is not dict
                or len(data['baselines']) > 32
                or type(data.get('services')) is not list or len(data['services']) > 128):
            raise ValueError('invalid_assessment_store')
        return data

    def _save(self,data):
        raw = json.dumps(data,allow_nan=False,separators=(',',':'))
        if len(raw.encode('utf-8')) > 65536:
            raise ValueError('assessment_store_capacity')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(raw,encoding='utf-8')
        temp.replace(self.path)

    def set_baseline(self,key,evidence,*,confirmed=False):
        if not confirmed or not _text(key) or not comparable(evidence,evidence):
            raise ValueError('baseline_requires_explicit_valid_reference')
        data = self.load()
        if key not in data['baselines'] and len(data['baselines']) >= 32:
            raise ValueError('baseline_capacity')
        data['baselines'][key] = encode(evidence)
        self._save(data)

    def baseline(self,key,current):
        raw = self.load()['baselines'].get(key)
        if raw is None:
            return None
        reference = decode(raw)
        return reference if comparable(current,reference) else None

    def complete_service(self,policy,*,timestamp,confirmed=False,counter=None,counter_id=None):
        if (not confirmed or not numeric(timestamp)
                or counter is not None and not numeric(counter)
                or counter_id is not None and not _text(counter_id)):
            raise ValueError('service_requires_confirmation')
        data = self.load()
        record = dict(task=policy.task_id,device=policy.device,basis=policy.basis,
                      timestamp=timestamp,counter=counter,counter_id=counter_id)
        data['services'] = (data['services']+[record])[-128:]
        self._save(data)

    def invalidate_device(self,device):
        data = self.load()
        data['baselines'] = {k:v for k,v in data['baselines'].items()
                             if v.get('device') != device}
        self._save(data)
