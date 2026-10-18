"""Bounded on-demand assessment facade. Never starts physical checks."""
from collections import OrderedDict
from maintenance_assessment import assessment_plan, observations, assess

class MaintenanceAssessment:
    def __init__(self,capacity=128):
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ValueError('invalid_assessment_capacity')
        self.capacity = capacity
        self._latest = OrderedDict()
        self._identity = None

    def ingest(self,result,method,state):
        identity = (state.epoch,id(state.settings))
        if identity != self._identity:
            self._latest.clear()
            self._identity = identity
        for item in observations(result,method):
            key = (item.feature,item.device)
            self._latest.pop(key,None)
            self._latest[key] = item
            while len(self._latest)>self.capacity:
                self._latest.popitem(last=False)

    def report(self,snapshot,rows):
        if snapshot is None or (snapshot.epoch,snapshot.config_marker) != self._identity:
            evidence = ()
        else:
            evidence = tuple(self._latest.values())
        plan = assessment_plan(snapshot,rows)
        return plan,assess(plan,evidence)

    def clear(self):
        self._latest.clear()
        self._identity = None
