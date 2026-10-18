"""Evidence-based findings. Threshold policies must identify their source."""
from dataclasses import dataclass
import math
from maintenance_assessment_model import Finding, comparable, _text

@dataclass(frozen=True, slots=True)
class MetricPolicy:
    feature: str
    key: str
    lower: float | None = None
    upper: float | None = None
    source: str = ''
    version: int = 1

    def __post_init__(self):
        from maintenance_catalog import definition_for
        definition_for(self.feature)
        if (not _text(self.key) or not _text(self.source)
                or type(self.version) is not int or self.version<1
                or self.lower is None and self.upper is None):
            raise ValueError('invalid_metric_policy')
        for value in (self.lower,self.upper):
            if value is not None and (type(value) not in (float,int) or not math.isfinite(value)):
                raise ValueError('invalid_metric_policy')
        if self.lower is not None and self.upper is not None and self.lower>self.upper:
            raise ValueError('invalid_metric_policy')

def observed_finding(item):
    """Interpret explicit firmware facts, not physical diagnoses."""
    values = dict(item.evidence)
    state,message = None,None
    if item.status not in ('OBSERVED','PASSED','PASSED_USER','OBSERVED_USER'):
        return None
    if item.feature=='S03':
        bits = values.get('throttled_bits')
        if type(bits) is int and bits>=0:
            if bits & 0xf:
                state,message = 'attention','system.throttle_active'
            elif bits & 0xf0000:
                state,message = 'attention','system.throttle_history'
            else:
                state,message = 'clear','system.no_throttle_reported'
    elif item.feature=='S08':
        value = values.get('webhooks_state')
        if value in ('error','shutdown'):
            state,message = 'issue','system.klipper_unavailable'
        elif values.get('configuration_warnings',0)>0:
            state,message = 'attention','system.configuration_warnings'
        elif value=='ready':
            state,message = 'clear','system.klipper_ready'
    elif item.feature=='M07':
        count = values.get('fault_count')
        if type(count) is int and count>=0:
            state,message = ('attention','driver.fault_reported') if count else ('clear','driver.no_fault_reported')
    elif item.feature=='S07':
        value = values.get('bus_state')
        if value in ('off','bus-off','passive','error-passive'):
            state,message = 'attention','system.can_state_review'
    if state is None:
        return None
    return Finding('fact.'+item.feature,item.device,state,message,(item.feature,))

def metric_finding(item,policy):
    if item.feature!=policy.feature or item.status not in (
            'PASSED','PASSED_USER','OBSERVED','FAILED_METRIC'):
        return None
    value = dict(item.evidence).get(policy.key)
    if type(value) not in (int,float) or not math.isfinite(value):
        return None
    outside = (policy.lower is not None and value<policy.lower
               or policy.upper is not None and value>policy.upper)
    return Finding('metric.'+item.feature,item.device,'attention' if outside else 'clear',
        'metric.outside_policy' if outside else 'metric.within_policy',(item.feature,),
        confidence='measured')

def trend_finding(current,baseline,key,*,relative_limit,source):
    if (not _text(source) or type(relative_limit) not in (int,float)
            or not math.isfinite(relative_limit) or relative_limit<=0):
        raise ValueError('invalid_trend_policy')
    if not comparable(current,baseline):
        return None
    a = next((m for m in current.measurements if m.key==key),None)
    b = next((m for m in baseline.measurements if m.key==key),None)
    if a is None or b is None or a.unit!=b.unit or b.value==0:
        return None
    changed = abs((a.value-b.value)/b.value)>relative_limit
    return Finding('trend.'+current.feature,current.device,'attention' if changed else 'clear',
        'trend.changed_review_conditions' if changed else 'trend.within_policy',
        (current.feature,),confidence='indicative')
