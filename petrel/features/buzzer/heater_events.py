"""Shared dashboard readiness and per-heater, live-delta completion tracking."""
import math
import re

COOLING_LIMITS = {'heater_bed': 40.0}
DEFAULT_COOLING_LIMIT = 50.0


def heater_name(name):
    return (isinstance(name, str) and
            (name == 'heater_bed' or re.fullmatch(r'extruder\d*', name) is not None
             or name.startswith('heater_generic ')))


def heater_ready(actual, target, previous=False):
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in (actual, target)):
        return None
    return target > 0 and abs(actual - target) <= (3.0 if previous else 2.0)


class HeaterEvents:
    def __init__(self):
        self.states = {}

    def reset(self):
        self.states.clear()

    def update(self, name, values, baseline=False):
        actual, target = values.get('temperature'), values.get('target')
        old = self.states.get(name)
        ready = heater_ready(actual, target, old['ready'] if old else False)
        if ready is None or target < 0:
            self.states.pop(name, None)
            return ()
        limit = COOLING_LIMITS.get(name, DEFAULT_COOLING_LIMIT)
        if baseline or old is None:
            self.states[name] = dict(target=target, actual=actual, ready=ready,
                heating=target > 0 and not ready, cooling=target == 0 and actual >= limit)
            return ()
        heating, cooling = old['heating'], old['cooling']
        if target != old['target']:
            # New target = new cycle. A target already satisfied is not a cycle.
            heating = target > 0 and not ready
            cooling = target == 0 and max(actual, old['actual']) >= limit
        events = []
        if target > 0:
            cooling = False
            if heating and ready:
                events.append('HEATING_DONE')
                heating = False
        else:
            heating = False
            if cooling and actual < limit:
                events.append('COOLING_DONE')
                cooling = False
        self.states[name] = dict(target=target, actual=actual, ready=ready,
                                heating=heating, cooling=cooling)
        return tuple(events)
