"""Capability-scoped assessment planning and conservative result interpretation."""
from dataclasses import dataclass
from maintenance_catalog import definition_for
from maintenance_assessment_model import Finding

_GROUPS = {'F':'cooling','H':'thermal','M':'motion','P':'geometry',
           'R':'vibration','E':'filament','S':'system','O':'auxiliary'}
_SUCCESS = frozenset(('PASSED','PASSED_USER','OBSERVED_USER','OBSERVED'))
_FAILURE = frozenset(('FAILED','FAILED_USER','FAILED_METRIC'))

@dataclass(frozen=True, slots=True)
class Observation:
    feature: str
    device: str | None
    status: str
    reason: str
    method: int | None
    evidence: tuple
    restored: bool | None
    conditions: tuple = ()
    operation_id: str = ''

@dataclass(frozen=True, slots=True)
class AssessmentPlan:
    topic: str
    device: str | None
    rows: tuple
    checks: tuple

def assessment_plan(snapshot, rows):
    """Intersect trusted registered plans with the current discovery epoch."""
    from maintenance_planner import PlannedTest
    if snapshot is None:
        return ()
    groups = {}
    for row in rows:
        if (not isinstance(row, PlannedTest) or not row.visible
                or row.epoch != snapshot.epoch or row.config_marker != snapshot.config_marker
                or not row.adapter_id
                or not snapshot.method(row.feature_id, row.device) & row.method):
            continue
        key = (_GROUPS[row.feature_id[0]], row.device)
        items = groups.setdefault(key, [])
        if row not in items:
            items.append(row)
    result = []
    for (topic, device), items in groups.items():
        checks = []
        for row in items:
            # The existing H01 adapter produces these seven component outcomes.
            feature = 'H01' if row.feature_id in ('H05','H06','H07','H08','H09','H13') and any(
                r.feature_id == 'H01' for r in items) else row.feature_id
            if feature not in checks:
                checks.append(feature)
        result.append(AssessmentPlan(topic,device,tuple(items),tuple(checks)))
    return tuple(result)

def observations(result, method=None):
    """Preserve bounded scalar evidence. Never parse human-facing reason text."""
    children = getattr(result,'components',())
    outcomes = children or (result,)
    if len(outcomes) > 7:
        raise ValueError('too_many_components')
    found = []
    for outcome in outcomes:
        feature = outcome.feature_id
        definition_for(feature)
        fields = []
        for key,value in getattr(outcome,'evidence',())[:32]:
            from maintenance_records import safe_scalar
            if isinstance(key,str) and len(key)<=48 and safe_scalar(value) is not None:
                fields.append((key,value))
        found.append(Observation(feature,getattr(outcome,'device',None),
            getattr(outcome,'status',None) or 'OBSERVED',getattr(outcome,'reason',''),
            method,tuple(fields),getattr(outcome,'restore_verified',None),
            getattr(outcome,'conditions',()),getattr(outcome,'operation_id','')))
    return tuple(found)

def assess(plan, evidence):
    """Return findings only for currently supported exact feature/device pairs."""
    allowed = {(r.feature_id,r.device) for p in plan for r in p.rows}
    latest = {}
    for item in evidence:
        if isinstance(item,Observation) and (item.feature,item.device) in allowed:
            latest[(item.feature,item.device)] = item
    findings = []
    for feature,device in sorted(allowed,key=lambda x:(x[0],x[1] or '')):
        item = latest.get((feature,device))
        if item is None:
            state,message,confidence = 'unknown','check.not_yet_measured','observed'
        elif item.status not in _SUCCESS | _FAILURE:
            state,message,confidence = 'unknown','check.not_completed','observed'
        elif item.status in _FAILURE:
            state,message,confidence = 'attention','check.requires_review','indicative'
        elif item.method in (8,16):
            state,message,confidence = 'unknown',('calibration.completed' if item.method == 8 else 'information.available'),'observed'
        else:
            state,message = 'clear','check.completed_in_scope'
            confidence = 'user_verified' if 'USER' in item.status else 'observed'
        actions = ()
        if item and item.status == 'FAILED_METRIC' and feature in ('H07','H08'):
            # Suggest only the actually available PID flow for this heater.
            pid = next((f for f in ('H02','H03','H04') if (f,device) in allowed),None)
            message = 'thermal.overshoot_review' if feature=='H07' else 'thermal.stability_review'
            actions = (pid,) if pid else ()
        finding = Finding('check.'+feature,device,state,message,(feature,),actions,confidence)
        if item is not None:
            from maintenance_assessment_rules import observed_finding
            finding = observed_finding(item) or finding
        findings.append(finding)
    return tuple(findings)
