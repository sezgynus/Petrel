"""Bounded, explicit width captures; never extrapolated lifetime usage."""
from configuration_identity import stable_digest, legacy_digest
import json
from pathlib import Path
from time import time
from maintenance_motion import number

def capture(device,settings,version,diameter):
    target = Path.home()/'.config'/'Petrel'/'maintenance-width-history.json'
    key = stable_digest((device,settings,version))
    records = {}
    try:
        if target.stat().st_size <= 65536:
            data = json.loads(target.read_text(encoding='utf-8'))
            if isinstance(data,dict) and data.get('version')==1 and isinstance(data.get('records'),dict):
                records = data['records']
    except (OSError,ValueError,TypeError):
        pass
    if len(records)>8:
        raise ValueError('width_history_capacity')
    old_key = legacy_digest((device,settings,version))
    if key not in records and old_key in records:
        records[key] = records.pop(old_key)
    prior = records.get(key,[])
    if not isinstance(prior,list) or len(prior)>64 or any(not isinstance(p,list) or len(p)!=2 or not all(number(v) for v in p) or not 0 < p[1] < 5 for p in prior):
        raise ValueError('width_history_invalid')
    if key not in records and len(records)>=8:
        raise ValueError('width_history_capacity')
    prior = (prior+[[time(),float(diameter)]])[-64:]
    records[key] = prior
    target.parent.mkdir(parents=True,exist_ok=True)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps({'version':1,'records':records}),encoding='utf-8')
    temp.replace(target)
    values = [p[1] for p in prior]
    return (('captures',len(values)),('minimum_mm',min(values)),('maximum_mm',max(values)),
            ('mean_mm',sum(values)/len(values)),('coverage','explicit_captures_only'))
