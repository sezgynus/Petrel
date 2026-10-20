"""On-demand bounded record operations for the encoder UI; shared worker only."""
from pathlib import Path
from time import time
from maintenance_assessment_store import AssessmentStore, ServicePolicy, service_due
from maintenance_records import read_json
from maintenance_usage import metric_counter

TASKS={'inspect_clean':'Inspect and clean','nozzle_inspect':'Inspect nozzle','lubricate':'Lubricate mechanism'}


def request(worker,operation,*,policy=None,devices=(),history=False,usage_provider=None):
    """Return a Future. Calling this function never performs synchronous disk I/O."""
    if operation not in ('load','save_policy','complete','remove_policy'):
        raise ValueError('unknown_maintenance_record_operation')
    if operation!='load' and not isinstance(policy,ServicePolicy):
        raise ValueError('service_policy_required')
    if operation not in ('load','remove_policy') and policy.device not in devices:
        raise ValueError('service_device_no_longer_available')
    def work():
        store=AssessmentStore(Path.home()/'.config'/'Petrel'/'maintenance-assessment.json')
        if operation=='save_policy': store.set_service_policy(policy)
        if operation=='remove_policy': store.remove_service_policy(policy)
        policies=store.service_policies()
        usage=usage_provider() if callable(usage_provider) and any(
            p.basis in ('sampled_on_s','sampled_print_s') for p in policies+((policy,) if policy and operation!='remove_policy' else ())) else {}
        def counter(item):
            value=metric_counter(usage,item.device,item.basis)
            identity=usage.get('counter_id')
            from maintenance_assessment_store import numeric
            return (value,identity) if numeric(value) and isinstance(identity,str) and identity else (None,None)
        if operation=='complete':
            value,identity=counter(policy) if policy.basis in ('sampled_on_s','sampled_print_s') else (None,None)
            if policy.basis!='calendar_s' and value is None:
                raise ValueError('service_counter_unknown')
            store.complete_service(policy,timestamp=time(),confirmed=True,counter=value,counter_id=identity)
        tasks=[]
        for item in policies:
            if item.device not in devices: continue
            completed=store.latest_service(item.task_id,item.device,item.basis)
            value,identity=counter(item)
            tracking=store.tracking_start(item)
            if completed is None and tracking is None and (
                    item.basis=='calendar_s' or value is not None):
                # Migrated legacy policies start at their first verified read.
                # Past untracked use must not be attributed to the new cycle.
                tracking=store.begin_tracking(item,timestamp=time(),
                    counter=value,counter_id=identity)
            reference=completed if completed is not None else tracking
            last=dict(completed) if completed is not None else {}
            if tracking is not None and completed is None:
                last['_tracking_started_at']=tracking.get('started_at')
            if item.basis=='calendar_s':
                stamp=(completed.get('timestamp') if completed is not None else
                       tracking.get('started_at') if tracking is not None else None)
                due=service_due(item,now=time(),last_at=stamp)
            else:
                previous=reference.get('counter') if reference else None
                previous_id=reference.get('counter_id') if reference else None
                due=service_due(item,now=time(),current=value,previous=previous,
                    continuity=identity is not None,counter_id=identity,
                    previous_counter_id=previous_id)
                if (value is not None and previous is not None and
                        identity is not None and identity==previous_id and
                        value>=previous):
                    last['_sampled_elapsed_s']=value-previous
                else:
                    last['_tracking_paused']=True
            tasks.append((item,last or None,due))
        records=()
        if history:
            data=read_json('maintenance-history.json',{'version':1,'records':[]})
            raw=data.get('records',())
            if not isinstance(raw,list) or len(raw)>64:
                raise ValueError('invalid_maintenance_history')
            # This store was created by the bounded sanitized result recorder.
            records=tuple(dict(item) for item in reversed(raw) if isinstance(item,dict))
        return tuple(tasks),records
    return worker.submit(work,queue_timeout=8)

