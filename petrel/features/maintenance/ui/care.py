"""Bounded, pure care presentation. Progress is elapsed policy time, never wear."""
from dataclasses import dataclass
import math
from petrel.features.maintenance.records.ui_requests import TASKS
from petrel.features.maintenance.records.care import task_label
from petrel.features.maintenance.ui.experience import device_name

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
    """Show actually sampled progress without claiming exact lifetime coverage."""
    from petrel.features.maintenance.assessment.store import service_due, numeric
    result=[]
    for policy,last,cached in tasks[:64]:
        if policy.device not in devices and policy.basis!='travel_mm':
            continue
        state=cached
        progress=remaining=None
        if policy.basis=='calendar_s':
            stamp=(last.get('timestamp',last.get('_tracking_started_at'))
                   if last else None)
            state=service_due(policy,now=now,last_at=stamp)
            if state!='unknown':
                elapsed=now-stamp
                progress=min(1.,max(0.,elapsed/policy.interval))
                remaining=policy.interval-elapsed
            status=('Service due' if state=='due' else
                    '%dd left'%max(1,math.ceil(remaining/86400))
                    if remaining is not None else 'Tracking starting')
        else:
            # The observed time is valid. Missing intervals only prevent a
            # definitive "not due" claim; they do not invalidate samples.
            elapsed=last.get('_sampled_elapsed_s') if last else None
            if numeric(elapsed):
                progress=min(1.,elapsed/policy.interval)
                def hours(value):
                    return ('%.1f'%value).rstrip('0').rstrip('.')
                status=('Service due' if state=='due' else
                        (hours(elapsed/1000.)+'/'+hours(policy.interval/1000.)+'m recorded')
                        if policy.basis in ('travel_mm','filament_mm') else
                        (str(int(elapsed))+'/'+str(int(policy.interval))+' events recorded')
                        if policy.basis in ('observed_trigger_count','trigger_count') else
                        hours(elapsed/3600.)+'/'+hours(policy.interval/3600.)+'h recorded')
            elif state=='due':
                progress=1.
                status='Service due'
            else:
                state='unknown'
                status='Tracking paused' if last and last.get('_tracking_paused') else 'Tracking starting'
        task=task_label(policy.task_id,policy.device)
        name=device_name(policy.device)
        label=(name+' / '+task)
        result.append(CareItem(policy,last,state,label,status,progress,remaining))
    return tuple(sorted(result,key=lambda x:(0 if x.state=='due' else 1 if x.remaining is not None else 2,
        x.remaining if x.remaining is not None else 0,x.label)))
