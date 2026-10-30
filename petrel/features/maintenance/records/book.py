"""Bounded result history, sampled usage and sanitized explicit report export."""
from collections.abc import Mapping
from configuration_identity import stable_digest
import json
import logging
from pathlib import Path
import re
import uuid
from threading import Lock
from time import monotonic, time
from petrel.features.maintenance.domains.motion.program import number


# At most 64 live descriptors; reserve another inventory for retired devices.
# Preserve every legacy counter and identity within the existing 64 KiB file.
MAX_USAGE_COUNTERS = 128
MAX_LEGACY_USAGE_COUNTERS = MAX_USAGE_COUNTERS
MAX_RECORD_BYTES = 65536


def _encode(value):
    return json.dumps(value,ensure_ascii=True,separators=(',',':'))


def _history_with_results(records, items):
    """Retain the complete newest group; evict oldest history by count AND bytes."""
    kept = (records+items)[-64:]
    sizes = [len(_encode(item)) for item in kept]
    size = len(_encode({'version':1,'records':[]})) + sum(sizes) + max(0,len(kept)-1)
    removed = 0
    while size > MAX_RECORD_BYTES and len(kept)-removed > len(items):
        size -= sizes[removed] + 1
        removed += 1
    if size > MAX_RECORD_BYTES:
        raise ValueError('maintenance_result_group_capacity')
    return {'version':1,'records':kept[removed:]}


class ResultWrite:
    """One local transaction, callable by its worker or shutdown finalizer."""
    def __init__(self, work):
        self._work = work
        self._lock = Lock()
        self._attempted = False
        self._error = None

    def __call__(self):
        with self._lock:
            if self._attempted:
                if self._error is not None:
                    raise self._error
                return
            self._attempted = True
            try:
                self._work()
            except Exception as error:
                self._error = error
                raise
            finally:
                self._work = None


def root():
    return Path.home()/'.config'/'Petrel'


def read_json(name,default):
    path = root()/name
    try:
        if path.stat().st_size > MAX_RECORD_BYTES:
            raise ValueError('maintenance_record_size')
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) and value.get('version')==1 else default
    except FileNotFoundError:
        return default


def write_json(name,value):
    target = root()/name
    raw = _encode(value)
    if len(raw)>MAX_RECORD_BYTES:
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
        self._record_jobs = {}
        self._closed = False
        self._inventory_key = None
        self._metrics = ()
        self.usage_omitted = 0
        self._capacity_rejected = set()
        self._observed = set()
        from petrel.features.maintenance.records.travel import TravelLedger
        self.travel = TravelLedger()
        from petrel.features.maintenance.records.sensor_usage import SensorUsage
        self.sensors = SensorUsage()
        from petrel.features.maintenance.records.sensor_usage import SensorEventLedger
        self.sensor_events = SensorEventLedger()

    def record(self,result,method,state,plan=None):
        if self._closed:
            self.errors += 1
            return
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
            digest = (stable_digest(state.settings)
                      if marker == id(state.settings) else None)
            for item in items:
                item['config_digest'] = digest
            with self._disk:
                data = read_json('maintenance-history.json',{'version':1,'records':[]})
                records = data.get('records')
                if not isinstance(records,list) or len(records)>64:
                    raise ValueError('maintenance_history_invalid')
                write_json('maintenance-history.json',_history_with_results(records,items))
        job = ResultWrite(work)
        try:
            # This is a bounded, exactly-once local write, not a staleable read.
            # Keep it queued until dispatch; orderly close finalizes cancellations.
            future = self._worker.submit(job,queue_timeout=None)
            self._record_futures.append(future)
            self._record_jobs[future] = job
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
                logging.warning('Maintenance result record was not confirmed')
            self._record_jobs.pop(future, None)
        self._record_futures = pending
        return self.errors != before

    def note(self,state,now=None,*,snapshot=None):
        """No I/O; bounded lower-bound sampled ON time, never exact lifetime."""
        if self._closed:
            return
        self.poll_records()
        now = monotonic() if now is None else now
        self.travel.note(state)
        active = {}
        key = (state.epoch,id(state.settings))
        if state.ready and key!=self._inventory_key:
            from petrel.features.maintenance.records.usage import usage_metrics
            if (snapshot is not None and snapshot.epoch==state.epoch
                    and snapshot.config_marker==id(state.settings)):
                self._metrics, self.usage_omitted = snapshot.usage_metrics, snapshot.usage_omitted
            else:
                self._metrics, self.usage_omitted = usage_metrics(getattr(state, 'objects', ()),state.settings)
            self._observed.clear()
            self._capacity_rejected.clear()
            self._inventory_key = key
            self._last = None
        self.sensor_events.note(state)
        if state.ready:
            for metric in self._metrics:
                if metric.metric_id != 'sampled_on_s':
                    continue
                value = metric.active(state.status)
                if value is not None:
                    active[metric.device] = value
                    self._observed.add(metric.device)
            active['@printing'] = (state.status.get('print_stats',{}).get('state')=='printing'
                and state.status.get('virtual_sdcard',{}).get('is_active') is True
                and state.status.get('pause_resume',{}).get('is_paused') is False)
        with self._lock:
            for name in tuple(active):
                if name in self._capacity_rejected or (name not in self._usage
                        and name != '@printing' and len(self._usage) >= MAX_USAGE_COUNTERS):
                    active.pop(name)
                    self._capacity_rejected.add(name)
                elif name != '@printing':
                    self._usage.setdefault(name, 0.)
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
        self.travel.flush()
        self.sensor_events.counters()
        with self._lock:
            pending,self._usage = self._usage,{}
        try:
            data = read_json('maintenance-usage.json',{'version':1,'sampled_on_s':{}})
            counters = data.get('sampled_on_s',{})
            if not isinstance(counters,dict) or len(counters)>MAX_LEGACY_USAGE_COUNTERS:
                raise ValueError('maintenance_usage_invalid')
            rejected = set()
            for name,value in sorted(pending.items()):
                if name=='@printing': continue
                if name not in counters and len(counters) >= MAX_USAGE_COUNTERS:
                    rejected.add(name)
                    continue
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
            # No periodic rewrite for an unchanged valid ledger. The first
            # read still creates the durable identity required by service anchors.
            changed = bool(pending) or data.get('counter_id') is None
            if changed:
                data.update(version=1, sampled_on_s=counters,
                    sampled_print_s=printing+pending.get('@printing',0.), counter_id=identity,
                    coverage='sampled_lower_bound_not_lifetime', saved_at=time())
                write_json('maintenance-usage.json',data)
            if rejected:
                with self._lock:
                    self._capacity_rejected.update(rejected)
                self.errors += len(rejected)
                logging.warning('Maintenance usage capacity reached; new device counters not recorded')
        except Exception:
            with self._lock:
                for name,value in pending.items():
                    self._usage[name] = self._usage.get(name,0.)+value
            raise

    def close(self):
        """Finalize accepted local records once, including cancelled queued jobs."""
        if self._closed:
            return
        self._closed = True
        for future in self._record_futures:
            job = self._record_jobs[future]
            try:
                if future.cancel() or not future.done():
                    # cancel succeeds only before worker dispatch. ResultWrite's
                    # lock also waits for an already started local transaction;
                    # it NEVER repeats an attempted write, even after an error.
                    job()
                else:
                    future.result()
            except Exception:
                self.errors += 1
                logging.warning('Maintenance result record unconfirmed during shutdown')
        self._record_futures = []
        self._record_jobs.clear()
        try:
            self.flush()
        except Exception:
            self.errors += 1
            logging.warning('Maintenance usage tail unconfirmed during shutdown')

    def usage_status(self):
        """Small immutable view; no disk or network access on the UI owner."""
        with self._lock:
            active = self._last[2] if self._last is not None else {}
            return tuple((m.device, 'capacity' if m.device in self._capacity_rejected else
                          'observed' if m.device in active else
                          'paused' if m.device in self._observed else 'starting')
                         for m in self._metrics if m.metric_id == 'sampled_on_s')

    def service_counters(self):
        """Worker-only durable lower bounds, with a persisted ledger identity."""
        with self._disk:
            self._flush_locked()
            data=read_json('maintenance-usage.json',{})
        states = self.usage_status()
        with self._lock:
            printing = self._last is not None
        available = tuple((device,'sampled_on_s') for device,status in states if status=='observed')
        if printing: available += ((None,'sampled_print_s'),)
        result = {'counter_id':data.get('counter_id'),
                'sampled_on_s':dict(data.get('sampled_on_s',{})),
                'sampled_print_s':data.get('sampled_print_s'),
                'available_metrics':available}
        with self._disk:
            travel = self.travel.counters()
        result.update(travel)
        with self._disk:
            sensors = self.sensors.counters()
        result.update(sensors)
        result['available_metrics'] += tuple((d, 'observed_trigger_count')
                                            for d in sensors['sensor_available'])
        with self._disk:
            events = self.sensor_events.counters()
        result.update(events)
        result['available_metrics'] += tuple((d, 'trigger_count') for d in events['event_available'])
        if travel['travel_available']:
            result['available_metrics'] += tuple((axis,'travel_mm') for axis in travel['travel_mm'])
        return result

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
            states = self.usage_status() if callable(getattr(self,'usage_status',None)) else ()
            counts = data.get('sampled_on_s',{})
            if not isinstance(counts,dict) or len(counts)>MAX_USAGE_COUNTERS:
                raise ValueError('maintenance_usage_invalid')
            fields = (('coverage','sampled_lower_bound_not_lifetime'),
                      ('sampled_print_s',data.get('sampled_print_s',0.)))
            fields += tuple((name+'.sampled_on_s',round(value,1))
                for name,value in sorted(counts.items()) if number(value) and value>=0)
            fields += tuple((name+'.tracking_state',status) for name,status in states
                            if status!='observed')
            if hasattr(self,'travel'):
                with self._disk:
                    travel = self.travel.counters()
                fields += tuple((axis+'.travel_mm',round(value,1)) for axis,value in travel['travel_mm'].items())
                if travel['travel_mm']:
                    fields += (('travel_tracking','tracking' if travel['travel_available'] else 'paused'),)
            if hasattr(self, 'sensor_events'):
                with self._disk:
                    events = self.sensor_events.counters()
                fields += (('sensor_event_coverage', 'klipper_callback_totals'),)
                fields += tuple((d+'.trigger_count', n) for d, n in sorted(events['trigger_count'].items()))
                fields += tuple((d+'.event_kind', kind) for d, kind in sorted(self.sensor_events.kinds.items()))
                fields += tuple((d+'.event_tracking', 'capacity' if d in self.sensor_events.rejected else 'paused')
                    for d in events['trigger_count'] if d not in events['event_available'])
                fields += tuple((d+'.event_tracking', 'capacity')
                    for d in self.sensor_events.rejected if d not in events['trigger_count'])
            return fields + (('usage_slots_remaining',max(0,MAX_USAGE_COUNTERS-len(counts))),
                             ('usage_tracking_omitted',getattr(self,'usage_omitted',0)))
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
            with self._disk:
                sensors = self.sensors.counters()
                events = self.sensor_events.counters()
            write_json('maintenance-report.json',{'version':1,'generated_at':time(),'records':records,
                'sampled_print_s':safe_scalar(usage.get('sampled_print_s')),
                'usage_counter_id':safe_scalar(usage.get('counter_id')),
                'sensor_counter_id':sensors['sensor_counter_id'],
                'observed_trigger_count':sensors['observed_trigger_count'],
                'sensor_coverage':'legacy_sampled_history_paused',
                'event_counter_id':events['event_counter_id'],
                'trigger_count':events['trigger_count'],
                'sensor_event_coverage':'klipper_callback_totals',
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

