"""UI-independent bounded assessment API; persistence runs on shared worker."""
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
import math
from maintenance_assessment import assessment_plan, observations, assess
from maintenance_assessment_rules import metric_finding, trend_finding
from maintenance_assessment_store import AssessmentStore, service_due

@dataclass(frozen=True, slots=True)
class BackendReport:
    plans: tuple
    findings: tuple
    services: tuple = ()
    trends: tuple = ()

class MaintenanceAssessment:
    def __init__(self,capacity=128,*,clock=monotonic,max_age=300.):
        if (type(capacity) is not int or not 1 <= capacity <= 256
                or not callable(clock) or type(max_age) not in (int,float)
                or not math.isfinite(max_age) or max_age<=0):
            raise ValueError('invalid_assessment_capacity_or_age')
        self.capacity = capacity
        self._latest = OrderedDict()
        self._trends = OrderedDict()
        self._identity = None
        self._clock,self._max_age = clock,max_age

    def ingest(self,result,method,state):
        identity = (state.epoch,id(state.settings))
        if identity != self._identity:
            self.clear()
            self._identity = identity
        now = self._clock()
        for item in observations(result,method):
            key = (item.feature,item.device)
            self._trends=OrderedDict((k,value) for k,value in self._trends.items()
                if not (value[1].device==item.device and item.feature in value[1].evidence_features))
            self._latest.pop(key,None)
            self._latest[key] = (now,item)
            while len(self._latest)>self.capacity:
                self._latest.popitem(last=False)

    def _evidence(self,snapshot):
        if snapshot is None or (snapshot.epoch,snapshot.config_marker) != self._identity:
            return ()
        now = self._clock()
        return tuple(item for stamp,item in self._latest.values()
                     if 0 <= now-stamp <= self._max_age)

    def has_current_evidence(self,snapshot):
        return bool(self._evidence(snapshot))

    def current_operation(self,snapshot,operation_id):
        return bool(operation_id) and any(item.operation_id==operation_id for item in self._evidence(snapshot))

    def accept_trend(self,snapshot,operation_id,finding):
        from maintenance_assessment_model import Finding
        if not isinstance(finding,Finding) or not self.current_operation(snapshot,operation_id):
            return False
        key=(finding.rule_id,finding.device)
        self._trends.pop(key,None)
        self._trends[key]=(self._clock(),finding)
        while len(self._trends)>self.capacity: self._trends.popitem(last=False)
        return True

    def invalidate_trends(self,device):
        self._trends=OrderedDict((key,value) for key,value in self._trends.items()
                                 if value[1].device!=device)

    def report(self,snapshot,rows):
        evidence = self._evidence(snapshot)
        plan = assessment_plan(snapshot,rows)
        return plan,assess(plan,evidence)

    def detailed_report(self,snapshot,rows,*,metric_policies=(),services=(),trends=()):
        """Policies and records are explicit inputs, not defaults or UI heuristics.

        services: (ServicePolicy, feature_id, service_due keyword arguments).
        trends: (current Evidence, baseline Evidence, metric key, relative limit, source).
        Neither path dispatches tests, saves config or acknowledges maintenance.
        """
        if any(len(items)>128 for items in (metric_policies,services,trends)):
            raise ValueError('assessment_input_capacity')
        plan,base = self.report(snapshot,rows)
        allowed = {(r.feature_id,r.device) for p in plan for r in p.rows}
        findings = {(f.rule_id,f.device):f for f in base}
        for item in self._evidence(snapshot):
            if (item.feature,item.device) not in allowed:
                continue
            for policy in metric_policies:
                finding = metric_finding(item,policy)
                if finding is not None:
                    findings[(finding.rule_id,finding.device)] = finding
        tasks = []
        for policy,feature,arguments in services:
            # A declared task must bind to a supported actual target.
            if (feature,policy.device) in allowed:
                tasks.append((policy.task_id,policy.device,service_due(policy,**arguments)))
        now=self._clock()
        compared = [f for stamp,f in self._trends.values()
                    if 0<=now-stamp<=self._max_age and
                    any((feature,f.device) in allowed for feature in f.evidence_features)
                    and snapshot is not None and (snapshot.epoch,snapshot.config_marker)==self._identity]
        for current,baseline,key,limit,source in trends:
            if (current.feature,current.device) in allowed:
                finding = trend_finding(current,baseline,key,relative_limit=limit,source=source)
                if finding is not None:
                    compared.append(finding)
        return BackendReport(plan,tuple(findings.values()),tuple(tasks),tuple(compared))

    @staticmethod
    def storage_request(worker,path,operation,*args,**kwargs):
        """Only explicit requests mutate baselines/services. Errors stay on Future."""
        methods = {'set_baseline','baseline','complete_service','invalidate_device','load',
                   'set_service_policy','service_policies','latest_service'}
        if operation not in methods:
            raise ValueError('unsupported_assessment_storage_operation')
        return worker.submit(lambda:getattr(AssessmentStore(path),operation)(*args,**kwargs),
                             queue_timeout=8)

    def clear(self):
        self._latest.clear()
        self._trends.clear()
        self._identity = None


