"""Typed evidence bridge for live observations or sanitized saved results."""
from maintenance_assessment_model import Evidence, Measurement
from maintenance_assessment import Observation

UNITS = {
 'samples':'count','span_s':'s','rise_c':'degC',
 'heating_c_per_s':'degC/s','time_to_target_s':'s','overshoot_c':'degC',
 'stability_peak_to_peak_c':'degC','cooling_c_per_s':'degC/s',
 'temperature':'degC','cpu_temp_c':'degC','ambient_c':'degC',
 'power':'fraction','diameter_mm':'mm','minimum_mm':'mm','maximum_mm':'mm','mean_mm':'mm',
 'commanded_mm':'mm','measured_mm':'mm','error_mm':'mm','force_g':'g','change_g':'g',
 'reference_grams':'g','peak_hz':'Hz','belt_a_peak_hz':'Hz','belt_b_peak_hz':'Hz',
 'frequency_ratio':'ratio','pwm_lower':'M106_S','pwm_upper':'M106_S',
}
_METHOD = {1:'firmware',2:'user',4:'external',8:'firmware',16:'information'}

def typed_evidence(item,*,observed_at,config_digest='',verified_conditions=()):
    """Additional comparison conditions must be explicitly verified by caller.

    Unknown units are omitted, never guessed from a display string or reason.
    Numeric firmware observations and user confirmation retain separate meaning.
    """
    if not isinstance(item,Observation):
        raise ValueError('assessment_observation_required')
    conditions = dict(item.conditions)
    for key,value in verified_conditions:
        if key in conditions and conditions[key]!=value:
            raise ValueError('conflicting_assessment_condition')
        conditions[key]=value
    values = tuple(Measurement(key,value,UNITS[key]) for key,value in item.evidence
                   if key in UNITS and type(value) in (int,float))
    method = _METHOD.get(item.method)
    if method is None:
        raise ValueError('unknown_assessment_method')
    return Evidence(item.feature,item.device,method,item.status,observed_at,values,
                    tuple(conditions.items()),item.operation_id,config_digest,item.restored)

def saved_evidence(record):
    """Legacy history remains readable but cannot invent missing conditions."""
    item = Observation(record['feature'],record.get('device'),
        record['status'],record.get('reason',''),record.get('method'),
        tuple(tuple(p) for p in record.get('evidence',())),
        record.get('restore_verified'),tuple(tuple(p) for p in record.get('conditions',())),
        record.get('operation_id') or '')
    return typed_evidence(item,observed_at=record['timestamp'],
                          config_digest=record.get('config_digest') or '')
