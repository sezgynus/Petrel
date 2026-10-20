"""Explicit baseline and service policy storage; no assumed service intervals."""
from dataclasses import asdict, dataclass, replace
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
                or self.basis not in ('calendar_s','print_s','sampled_on_s','sampled_print_s','travel_mm')
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
    return 'unknown' if policy.basis in ('sampled_on_s','sampled_print_s') else 'not_due'

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

    def baseline(self,key,current,*,legacy_digest=None):
        raw = self.load()['baselines'].get(key)
        if raw is None:
            return None
        reference = decode(raw)
        if legacy_digest and reference.config_digest == legacy_digest:
            reference = replace(reference,config_digest=current.config_digest)
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

    def tracking_start(self,policy):
        """Get a tracking anchor without claiming a service was completed."""
        items=self.load().get('tracking',[])
        if type(items) is not list or len(items)>64:
            raise ValueError('invalid_service_tracking')
        return next((dict(row) for row in reversed(items)
                     if type(row) is dict and (row.get('task'),row.get('device'),row.get('basis'))
                     ==(policy.task_id,policy.device,policy.basis)),None)

    def begin_tracking(self,policy,*,timestamp,counter=None,counter_id=None):
        """Persist first observable use; never create a service-completion record."""
        if not isinstance(policy,ServicePolicy) or not numeric(timestamp):
            raise ValueError('invalid_tracking_start')
        if policy.basis!='calendar_s' and (
                not numeric(counter) or not _text(counter_id)):
            raise ValueError('tracking_counter_unavailable')
        data=self.load()
        items=data.get('tracking',[])
        if type(items) is not list or len(items)>64:
            raise ValueError('invalid_service_tracking')
        prior=next((dict(row) for row in reversed(items)
                    if type(row) is dict and
                    (row.get('task'),row.get('device'),row.get('basis'))
                    ==(policy.task_id,policy.device,policy.basis)),None)
        if prior is not None:
            return prior
        items=[row for row in items if not (type(row) is dict and
            (row.get('task'),row.get('device'))==(policy.task_id,policy.device))]
        if len(items)>=64:
            raise ValueError('tracking_capacity')
        record=dict(task=policy.task_id,device=policy.device,basis=policy.basis,
                    started_at=timestamp,counter=counter,counter_id=counter_id)
        data['tracking']=items+[record]
        self._save(data)
        return record

    def set_service_policy(self,policy):
        if not isinstance(policy,ServicePolicy):
            raise ValueError('invalid_service_policy')
        data = self.load()
        policies = data.get('policies',[])
        if type(policies) is not list or len(policies)>64:
            raise ValueError('invalid_service_policies')
        policies = [p for p in policies if (p.get('task_id'),p.get('device')) !=
                    (policy.task_id,policy.device)]
        if len(policies)>=64:
            raise ValueError('service_policy_capacity')
        data['policies'] = policies+[asdict(policy)]
        self._save(data)

    def remove_service_policy(self,policy):
        """Remove only an exact saved reminder; retain anchors and service history.

        An old confirmation must never delete a newly edited replacement.
        Repeating a successful removal is a harmless no-op.
        """
        if not isinstance(policy,ServicePolicy):
            raise ValueError('invalid_service_policy')
        data=self.load()
        items=data.get('policies',[])
        if type(items) is not list or len(items)>64:
            raise ValueError('invalid_service_policies')
        same=[item for item in items if (item.get('task_id'),item.get('device'))
              ==(policy.task_id,policy.device)]
        if not same:
            return False
        if len(same)!=1 or ServicePolicy(**same[0])!=policy:
            raise ValueError('service_policy_changed')
        data['policies']=[item for item in items if item is not same[0]]
        self._save(data)
        return True

    def service_policies(self):
        items = self.load().get('policies',[])
        if type(items) is not list or len(items)>64:
            raise ValueError('invalid_service_policies')
        return tuple(ServicePolicy(**item) for item in items)

    def latest_service(self,task_id,device,basis=None):
        return next((dict(item) for item in reversed(self.load()['services'])
                     if item.get('task')==task_id and item.get('device')==device
                     and (basis is None or item.get('basis')==basis)),None)

    def invalidate_device(self,device):
        data = self.load()
        data['baselines'] = {k:v for k,v in data['baselines'].items()
                             if v.get('device') != device}
        self._save(data)

