"""On-demand Moonraker native job-history totals for single-extruder care.

Read only from the existing maintenance worker. A tiny local identity protects
saved reminder anchors against detectable Moonraker history counter resets.
"""
import re
import uuid
from maintenance_records import read_json, write_json
from maintenance_usage import numeric

FILE = 'maintenance-filament-history.json'
BASIS = 'filament_mm'
DEVICE = 'extruder'
MAX_TOTAL = 2**53 - 1


def read_totals(body):
    result = body.get('result') if isinstance(body, dict) else None
    totals = result.get('job_totals') if isinstance(result, dict) else None
    if not isinstance(totals, dict):
        raise ValueError('filament_history_unavailable')
    used, jobs = totals.get('total_filament_used'), totals.get('total_jobs')
    if (not numeric(used) or used > MAX_TOTAL
            or type(jobs) is not int or not 0 <= jobs <= MAX_TOTAL):
        raise ValueError('filament_history_invalid')
    return float(used), jobs


def recorded_filament(client):
    current, jobs = read_totals(client.request(
        'GET', '/server/history/totals', request_timeout=2.0))
    state = read_json(FILE, {})
    if state and (type(state.get('version')) is not int or state['version'] != 1
                  or not isinstance(state.get('counter_id'), str)
                  or not re.fullmatch(r'[0-9a-f]{32}',state['counter_id'])
                  or not numeric(state.get('last_mm'))
                  or state['last_mm'] > MAX_TOTAL
                  or type(state.get('last_jobs')) is not int
                  or not 0 <= state['last_jobs'] <= MAX_TOTAL):
        raise ValueError('filament_history_identity_invalid')
    reset = not state or current < state['last_mm'] or jobs < state['last_jobs']
    if reset:
        state = dict(version=1, counter_id=uuid.uuid4().hex,
                     last_mm=current, last_jobs=jobs)
    changed = not reset and (current > state['last_mm'] or jobs > state['last_jobs'])
    if changed:
        state = dict(state,last_mm=current,last_jobs=jobs)
    if reset or changed:
        write_json(FILE,state)
    return {BASIS:{DEVICE:current},'filament_counter_id':state['counter_id'],
            'available_metrics':((DEVICE,BASIS),)}
