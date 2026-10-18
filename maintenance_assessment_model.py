"""Immutable assessment contracts. No I/O, commands, UI or implicit diagnosis."""
from dataclasses import dataclass
import math

def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 160

@dataclass(frozen=True, slots=True)
class Measurement:
    key: str
    value: float
    unit: str

    def __post_init__(self):
        if (not _text(self.key) or not _text(self.unit)
                or type(self.value) not in (int, float) or not math.isfinite(self.value)):
            raise ValueError('invalid_measurement')

@dataclass(frozen=True, slots=True)
class Evidence:
    feature: str
    device: str | None
    method: str
    status: str
    observed_at: float
    measurements: tuple = ()
    conditions: tuple = ()
    operation_id: str = ''
    config_digest: str = ''
    restored: bool | None = None

    def __post_init__(self):
        from maintenance_catalog import definition_for
        definition_for(self.feature)
        if (self.device is not None and not _text(self.device)
                or self.method not in ('sensor', 'firmware', 'user', 'external', 'information')
                or not _text(self.status)
                or type(self.observed_at) not in (int, float)
                or not math.isfinite(self.observed_at) or self.observed_at < 0
                or type(self.measurements) is not tuple or len(self.measurements) > 32
                or any(not isinstance(m, Measurement) for m in self.measurements)
                or len({m.key for m in self.measurements}) != len(self.measurements)
                or type(self.conditions) is not tuple or len(self.conditions) > 32
                or type(self.operation_id) is not str or len(self.operation_id) > 160
                or type(self.config_digest) is not str or len(self.config_digest) > 160
                or self.restored is not None and type(self.restored) is not bool):
            raise ValueError('invalid_assessment_evidence')
        keys = set()
        for pair in self.conditions:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError('invalid_condition')
            key, value = pair
            if not _text(key) or key in keys:
                raise ValueError('invalid_condition')
            keys.add(key)
            if not (type(value) is bool or _text(value)
                    or type(value) in (int, float) and math.isfinite(value)):
                raise ValueError('invalid_condition')

@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    device: str | None
    state: str
    message_key: str
    evidence_features: tuple = ()
    actions: tuple = ()
    confidence: str = 'observed'

    def __post_init__(self):
        if (not _text(self.rule_id) or not _text(self.message_key)
                or self.device is not None and not _text(self.device)
                or self.state not in ('clear', 'attention', 'issue', 'unknown')
                or self.confidence not in ('observed', 'user_verified', 'measured', 'indicative')
                or type(self.evidence_features) is not tuple
                or type(self.actions) is not tuple
                or any(not _text(x) for x in self.evidence_features + self.actions)):
            raise ValueError('invalid_finding')

def comparable(current, baseline):
    """A digest alone is insufficient: require complete equal test conditions."""
    required = {'profile_version', 'target_c', 'initial_band', 'fan_state', 'hardware_revision'}
    a, b = dict(current.conditions), dict(baseline.conditions)
    return (current.feature == baseline.feature and current.device == baseline.device
            and bool(current.config_digest) and current.config_digest == baseline.config_digest
            and required <= a.keys() and required <= b.keys()
            and all(a[k] == b[k] and a[k] not in ('unknown','unverified','not_tracked') for k in required)
            and current.method == baseline.method
            and current.status in ('PASSED', 'PASSED_USER', 'OBSERVED', 'FAILED_METRIC')
            and baseline.status in ('PASSED', 'PASSED_USER', 'OBSERVED'))
