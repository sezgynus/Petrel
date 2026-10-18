"""Bounded, pure care presentation. Progress is elapsed policy time, never wear."""
from dataclasses import dataclass
import math
from maintenance_ui_records import TASKS
from maintenance_experience import device_name

@dataclass(frozen=True, slots=True)
class CareItem:
    policy: object
    last: object
    state: str
    label: str
    detail: str
    progress: float | None
    remaining: float | None


def care_items(tasks, devices, now):
    """Use only present devices and explicit policies. Unknown coverage stays blank."""
    from maintenance_assessment_store import service_due, numeric
    result=[]
    for policy,last,cached in tasks[:64]:
        if policy.device not in devices:
            continue
        state=cached
        progress=remaining=None
        if policy.basis=='calendar_s':
            stamp=last.get('timestamp') if last else None
            state=service_due(policy,now=now,last_at=stamp)
            if state!='unknown':
                elapsed=now-stamp
                progress=min(1.,elapsed/policy.interval)
                remaining=policy.interval-elapsed
        elif state=='due':
            # Sampled counters can prove elapsed policy, not remaining lifetime.
            progress=1.
        else:
            state='unknown'
        status=('Due' if state=='due' else
                '%dd left'%max(1,math.ceil(remaining/86400)) if remaining is not None else
                'No service date' if not last else 'Coverage unknown')
        task=TASKS.get(policy.task_id,'Service task')
        name=device_name(policy.device)
        label=(name+' / '+task)
        result.append(CareItem(policy,last,state,label,status,progress,remaining))
    return tuple(sorted(result,key=lambda x:(0 if x.state=='due' else 1 if x.remaining is not None else 2,
        x.remaining if x.remaining is not None else 0,x.label)))
