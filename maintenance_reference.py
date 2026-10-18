"""Explicit, comparable heating-speed references on the existing I/O worker."""
from dataclasses import dataclass
from pathlib import Path
from time import time
import hashlib
import json
import math
from maintenance_assessment import Observation
from maintenance_assessment_bridge import typed_evidence
from maintenance_assessment_model import Finding, comparable
from maintenance_assessment_store import AssessmentStore


@dataclass(frozen=True,slots=True)
class ReferenceResult:
    heading: str
    lines: tuple
    operation_id: str
    finding: Finding | None = None


def heating_observation(result):
    parts=getattr(result,'components',()) or (result,)
    child=next((p for p in parts if getattr(p,'feature_id',None)=='H05'),None)
    if child is None or child.status not in ('PASSED_USER','FAILED_METRIC') or child.restore_verified is not True:
        raise ValueError('heating_reference_requires_completed_measurement')
    conditions=dict(child.conditions)
    initial=conditions.get('initial_temperature_c')
    if (type(initial) not in (int,float) or not math.isfinite(initial)
            or not conditions.get('fan_state') or not conditions.get('firmware_version')
            or not all(k in conditions for k in ('profile_version','target_c','duration_s'))
            or not child.operation_id):
        raise ValueError('heating_reference_conditions_missing')
    value=dict(child.evidence).get('heating_c_per_s')
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('heating_reference_metric_missing')
    return Observation('H05',child.device,child.status,child.reason,1,child.evidence,
        True,child.conditions,child.operation_id)


def request(worker,operation,result,state,*,confirmed=False,relative_limit=None,current=lambda:False):
    if operation not in ('save','compare','clear') or confirmed is not True:
        raise ValueError('reference_requires_explicit_confirmation')
    observation=heating_observation(result)
    if operation=='compare' and (type(relative_limit) not in (int,float)
            or not math.isfinite(relative_limit) or not .01<=relative_limit<=1.):
        raise ValueError('reference_limit_requires_explicit_policy')
    def work():
        if not current(): raise ValueError('reference_session_changed')
        initial=dict(observation.conditions)['initial_temperature_c']
        band=math.floor(initial/5)*5
        digest=hashlib.sha256(json.dumps(state.settings,sort_keys=True,default=str).encode()).hexdigest()
        evidence=typed_evidence(observation,observed_at=time(),config_digest=digest,
            verified_conditions=(('initial_band','%d..%d C'%(band,band+5)),
                ('hardware_revision','operator_confirmed_unchanged')))
        store=AssessmentStore(Path.home()/'.config'/'Petrel'/'maintenance-assessment.json')
        key='heating-speed:'+str(evidence.device)
        if operation=='clear':
            store.invalidate_device(evidence.device)
            return ReferenceResult('Reference removed',('Run a new check after hardware changes.',),evidence.operation_id)
        if operation=='save':
            value=next(m.value for m in evidence.measurements if m.key=='heating_c_per_s')
            if value<=0: raise ValueError('reference_requires_positive_heating_rate')
            store.set_baseline(key,evidence,confirmed=True)
            return ReferenceResult('Heating reference saved',('Only the measured heating speed is a reference.',
                'Hardware health and remaining life are not certified.'),evidence.operation_id)
        baseline=store.baseline(key,evidence)
        if baseline is None or not comparable(evidence,baseline):
            return ReferenceResult('No compatible reference',('Target, duration, start-temperature band,',
                'fan state, firmware and configuration must match.'),evidence.operation_id)
        before=next((m.value for m in baseline.measurements if m.key=='heating_c_per_s'),0)
        after=next(m.value for m in evidence.measurements if m.key=='heating_c_per_s')
        if before<=0: raise ValueError('reference_requires_positive_heating_rate')
        change=(after-before)/before
        changed=abs(change)>relative_limit
        heading=('Heating is slower than reference' if change<0 else 'Heating changed from reference') if changed else 'Heating change within your limit'
        finding=Finding('trend.H05',evidence.device,'attention' if changed else 'clear',
            'trend.changed_review_conditions' if changed else 'trend.within_policy',('H05',),confidence='indicative')
        return ReferenceResult(heading,('Measured change: %+.1f%%'%(change*100),
            'Your review limit: %.0f%%'%(relative_limit*100),
            'Review cooling, mounting and supply conditions.',
            'This does not identify a failed heater cartridge.'),evidence.operation_id,finding)
    return worker.submit(work,queue_timeout=8)
