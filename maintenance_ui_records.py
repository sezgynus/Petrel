"""On-demand bounded record operations for the encoder UI; shared worker only."""
from pathlib import Path
from time import time
from maintenance_assessment_store import AssessmentStore, ServicePolicy, service_due
from maintenance_records import read_json

TASKS={'inspect_clean':'Inspect and clean','nozzle_inspect':'Inspect nozzle','lubricate':'Lubricate mechanism'}


def request(worker,operation,*,policy=None,devices=(),history=False):
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
        if operation=='complete': store.complete_service(policy,timestamp=time(),confirmed=True)
        policies=store.service_policies()
        tasks=[]
        for item in policies:
            if item.device not in devices: continue
            last=store.latest_service(item.task_id,item.device)
            due=service_due(item,now=time(),last_at=last.get('timestamp') if last else None)
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
