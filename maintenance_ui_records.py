"""On-demand bounded record operations for the encoder UI; shared worker only."""
from pathlib import Path
from time import time
from maintenance_assessment_store import AssessmentStore, ServicePolicy, service_due
from maintenance_records import read_json

TASKS={'inspect_clean':'Inspect and clean','nozzle_inspect':'Inspect nozzle','lubricate':'Lubricate mechanism'}


def request(worker,operation,*,policy=None,devices=(),history=False,usage_provider=None):
    """Return a Future. Calling this function never performs synchronous disk I/O."""
    if operation not in ('load','save_policy','complete'):
        raise ValueError('unknown_maintenance_record_operation')
    if operation!='load' and not isinstance(policy,ServicePolicy):
        raise ValueError('service_policy_required')
    if operation!='load' and policy.device not in devices:
        raise ValueError('service_device_no_longer_available')
    def work():
        store=AssessmentStore(Path.home()/'.config'/'Petrel'/'maintenance-assessment.json')
        if operation=='save_policy': store.set_service_policy(policy)
        policies=store.service_policies()
        usage=usage_provider() if callable(usage_provider) and any(
            p.basis in ('sampled_on_s','sampled_print_s') for p in policies+((policy,) if policy else ())) else {}
        def counter(item):
            value=(usage.get('sampled_print_s') if item.basis=='sampled_print_s' else
                   usage.get('sampled_on_s',{}).get(item.device))
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
            last=store.latest_service(item.task_id,item.device,item.basis)
            value,identity=counter(item)
            due=service_due(item,now=time(),last_at=last.get('timestamp') if last else None,
                current=value,previous=last.get('counter') if last else None,
                continuity=identity is not None,counter_id=identity,
                previous_counter_id=last.get('counter_id') if last else None)
            tasks.append((item,last,due))
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

