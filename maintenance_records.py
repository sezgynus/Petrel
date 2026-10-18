"""Bounded result history, sampled usage and sanitized explicit report export."""
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
import uuid
from threading import Lock
from time import monotonic, time
from maintenance_motion import number


def root():
    return Path.home()/'.config'/'Petrel'


def read_json(name,default):
    path = root()/name
    try:
        if path.stat().st_size > 65536:
            raise ValueError('maintenance_record_size')
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) and value.get('version')==1 else default
    except FileNotFoundError:
        return default


def write_json(name,value):
    target = root()/name
    raw = json.dumps(value,ensure_ascii=True,separators=(',',':'))
    if len(raw)>65536:
        raise ValueError('maintenance_record_capacity')
    target.parent.mkdir(parents=True,exist_ok=True)
    temp = target.with_suffix('.tmp')
    temp.write_text(raw,encoding='utf-8')
    temp.replace(target)


def safe_scalar(value):
    if type(value) is bool or number(value):
        return value
    if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_ .,:>+%=-]{1,96}',value):
        return value
    return None


class MaintenanceBook:
    def __init__(self,worker):
        self._worker = worker
        self._lock = Lock()
        self._disk = Lock()
        self._usage = {}
        self._last = None
        self._flush_at = monotonic()+300
        self._save = None
        self.errors = 0
        self._record_futures = []
        self._inventory_key = None
        self._names = ()
        self._observed = set()

    def record(self,result,method,state,plan=None):
        self.poll_records()
        if len(self._record_futures) >= 8:
            self.errors += 1
            return
        # A single thermal operation can produce seven independent feature
        # results. Persist them together in one bounded worker transaction.
        children = getattr(result, 'components', ())
        outcomes = children if children else (result,)
        if len(outcomes) > 7:
            return
        stamp = time()
        marker = getattr(plan, 'config_marker', id(state.settings))
        items = []
        for outcome in outcomes:
            feature = getattr(outcome, 'feature_id', '')
            if not re.fullmatch(r'[FHM PRESO][0-9]{2}'.replace(' ',''), str(feature)):
                return
            status = getattr(outcome, 'status', None) or 'OBSERVED'
            item = {'feature':feature,'device':safe_scalar(getattr(outcome,'device',None)),
                    'method':method,'status':safe_scalar(status),
                    'reason':safe_scalar(getattr(outcome,'reason','')),
                    'timestamp':stamp,'epoch':getattr(plan,'epoch',state.epoch),
                    'config_marker':marker,
                    'firmware':safe_scalar(state.software_version),'evidence':[],
                    'restore_verified':getattr(outcome,'restore_verified',None),
                    'operation_id':safe_scalar(getattr(outcome,'operation_id','')),
                    'conditions':[(k,safe_scalar(v)) for k,v in getattr(outcome,'conditions',())[:16]
                                  if isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9_.]{1,48}',k)
                                  and safe_scalar(v) is not None]}
            for key,value in getattr(outcome, 'evidence', ())[:16]:
                cleaned = safe_scalar(value)
                if cleaned is not None and isinstance(key,str) and re.fullmatch(r'[A-Za-z0-9_.]{1,48}',key):
                    item['evidence'].append((key,cleaned))
            items.append(item)
        def work():
            digest = (hashlib.sha256(json.dumps(state.settings,sort_keys=True,default=str).encode()).hexdigest()
                      if marker == id(state.settings) else None)
            for item in items:
                item['config_digest'] = digest
            data = read_json('maintenance-history.json',{'version':1,'records':[]})
            records = data.get('records')
            if not isinstance(records,list) or len(records)>64:
                raise ValueError('maintenance_history_invalid')
            write_json('maintenance-history.json',{'version':1,'records':(records+items)[-64:]})
        try:
            self._record_futures.append(self._worker.submit(work,queue_timeout=8))
            self.poll_records()
        except Exception:
            self.errors += 1

    def poll_records(self):
        """Consume completed writes on the owner; never wait or retry a write."""
        before = self.errors
        pending = []
        for future in self._record_futures:
            if not future.done():
                pending.append(future)
                continue
            try:
                future.result()
            except Exception:
                self.errors += 1
        self._record_futures = pending
        return self.errors != before

    def note(self,state,now=None):
        """No I/O; bounded lower-bound sampled ON time, never exact lifetime."""
        self.poll_records()
        now = monotonic() if now is None else now
        active = {}
        key = (state.epoch,id(state.settings))
        if state.ready and key!=self._inventory_key:
            self._observed.clear()
            self._names = tuple(name for name,cfg in state.settings.items()
                if name=='fan' or name.startswith(('fan_generic ','heater_fan ','controller_fan ','temperature_fan '))
                or isinstance(cfg,Mapping) and 'heater_pin' in cfg)[:16]
            self._inventory_key = key
        if state.ready:
            for name in self._names:
                values = state.status.get(name)
                if not isinstance(values,Mapping):
                    continue
                cfg = state.settings.get(name,{})
                key = 'power' if isinstance(cfg,Mapping) and 'heater_pin' in cfg else (
                      'speed' if name=='fan' or name.startswith(('fan_generic ','heater_fan ','controller_fan ','temperature_fan ')) else None)
                if key and number(values.get(key)):
                    active[name] = values[key]>0
                    self._observed.add(name)
            active['@printing'] = (state.status.get('print_stats',{}).get('state')=='printing'
                and state.status.get('virtual_sdcard',{}).get('is_active') is True
                and state.status.get('pause_resume',{}).get('is_paused') is False)
        with self._lock:
            for name in active:
                if name != '@printing': self._usage.setdefault(name, 0.)
            previous = self._last
            if previous is not None and state.epoch==previous[0]:
                dt = now-previous[1]
                if 0 < dt <= 2:
                    for name,on in active.items():
                        if on and previous[2].get(name) is True:
                            self._usage[name] = self._usage.get(name,0.)+dt
            self._last = (state.epoch,now,active) if state.ready else None
        if now>=self._flush_at and self._save is None:
            self._flush_at = now+300
            try:
                self._save = self._worker.submit(self.flush,queue_timeout=8)
            except Exception:
                self.errors += 1
        if self._save is not None and self._save.done():
            try:
                self._save.result()
            except Exception:
                self.errors += 1
            self._save = None

    def flush(self):
        with self._disk:
            self._flush_locked()

    def _flush_locked(self):
        with self._lock:
            pending,self._usage = self._usage,{}
        try:
            data = read_json('maintenance-usage.json',{'version':1,'sampled_on_s':{}})
            counters = data.get('sampled_on_s',{})
            if not isinstance(counters,dict) or len(counters)>32:
                raise ValueError('maintenance_usage_invalid')
            for name,value in pending.items():
                if name=='@printing': continue
                old = counters.get(name,0.)
                if not number(old) or old<0:
                    raise ValueError('maintenance_usage_invalid')
                counters[name] = old+value
            printing = data.get('sampled_print_s',0.)
            if not number(printing) or printing<0:
                raise ValueError('maintenance_print_usage_invalid')
            identity = data.get('counter_id')
            if identity is None: identity=uuid.uuid4().hex
            if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{32}',identity):
                raise ValueError('maintenance_usage_identity_invalid')
            write_json('maintenance-usage.json',{'version':1,'sampled_on_s':counters,
                'sampled_print_s':printing+pending.get('@printing',0.),'counter_id':identity,
                'coverage':'sampled_lower_bound_not_lifetime','saved_at':time()})
        except Exception:
            with self._lock:
                for name,value in pending.items():
                    self._usage[name] = self._usage.get(name,0.)+value
            raise

    def close(self):
        """Shutdown is outside drawing; preserve the final sampled tail."""
        try:
            self.flush()
        except Exception:
            self.errors += 1

    def service_counters(self):
        """Worker-only durable lower bounds, with a persisted ledger identity."""
        self.flush()
        data=read_json('maintenance-usage.json',{})
        counters=dict(data.get('sampled_on_s',{}))
        return {'counter_id':data.get('counter_id'),'sampled_on_s':counters,
                'sampled_print_s':data.get('sampled_print_s')}

    def read(self,feature):
        if feature=='S11':
            data = read_json('maintenance-history.json',{'version':1,'records':[]})
            records = data.get('records',[])
            if not isinstance(records,list) or len(records)>64:
                return ()
            result = [('recorded_results',len(records))]
            for i,item in enumerate(records[-5:]):
                if isinstance(item,dict):
                    result.append(('recent_'+str(i),str(item.get('feature',''))+' '+str(item.get('status',''))))
            return tuple(result)
        if feature=='S12':
            self.flush()
            data = read_json('maintenance-usage.json',{'version':1,'sampled_on_s':{}})
            return (('coverage','sampled_lower_bound_not_lifetime'),
                    ('sampled_print_s',data.get('sampled_print_s',0.)),)+tuple(
                (name[:40]+'.sampled_on_s',round(value,1))
                for name,value in data.get('sampled_on_s',{}).items() if number(value) and value>=0)[:16]
        if feature=='S20':
            self.flush()
            history = read_json('maintenance-history.json',{'version':1,'records':[]})
            usage = read_json('maintenance-usage.json',{'version':1,'sampled_on_s':{}})
            # Export only values created/allowlisted by this recorder.
            records = []
            for item in history.get('records',[])[-32:]:
                if isinstance(item,dict):
                    record = {k:safe_scalar(item.get(k)) for k in ('feature','device','method','status','reason','timestamp','epoch','firmware','config_marker','config_digest')}
                    record['restore_verified'] = item.get('restore_verified') if type(item.get('restore_verified')) is bool else None
                    record['operation_id'] = safe_scalar(item.get('operation_id'))
                    record['conditions'] = [(k,safe_scalar(v)) for k,v in item.get('conditions',[])[:16]
                        if isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9_.]{1,48}',k) and safe_scalar(v) is not None]
                    record['evidence'] = [(k,safe_scalar(v)) for k,v in item.get('evidence',[])[:16]
                        if isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9_.]{1,48}',k) and safe_scalar(v) is not None]
                    records.append(record)
            write_json('maintenance-report.json',{'version':1,'generated_at':time(),'records':records,
                'sampled_print_s':safe_scalar(usage.get('sampled_print_s')),
                'usage_counter_id':safe_scalar(usage.get('counter_id')),
                'usage':{k:v for k,v in usage.get('sampled_on_s',{}).items()
                         if safe_scalar(k) and number(v) and v>=0},
                'coverage':'sampled_lower_bound_not_lifetime'})
            return (('report_ready',True),('download','maintenance-report.json'),('results',len(records)))
        return ()

    def exported(self):
        path = root()/'maintenance-report.json'
        if not path.is_file() or path.stat().st_size>65536:
            return None
        return path.read_bytes()

