"""Small passive usage contracts, independent of actuator/test permissions.

Sources: Klipper Status Reference (fan, heater, output_pin, pwm_cycle_time).
An object-list entry establishes the documented field contract; each runtime
sample must still validate the value. No source state/configuration is retained.
"""
from dataclasses import dataclass
from math import isfinite

MAX_TRACKED_METRICS = 64
MAX_DEVICE_NAME = 96
FAN_PREFIXES = ('fan_generic ', 'heater_fan ', 'controller_fan ', 'temperature_fan ')
OUTPUT_PREFIXES = ('output_pin ', 'pwm_cycle_time ', 'pwm_tool ')


@dataclass(frozen=True, slots=True)
class UsageMetric:
    device: str
    field: str
    metric_id: str = 'sampled_on_s'
    unit: str = 's'

    def active(self, status):
        """None means unreadable, not OFF; booleans/NaN/negative fail closed."""
        from collections.abc import Mapping
        values = status.get(self.device)
        value = values.get(self.field) if isinstance(values, Mapping) else None
        if type(value) not in (int, float) or not isfinite(value) or value < 0:
            return None
        return value > 0


def usage_field(name):
    """Only documented object classes; never infer a source from a pin key."""
    if not isinstance(name, str) or not 0 < len(name) <= MAX_DEVICE_NAME:
        return None
    if name == 'fan' or name.startswith(FAN_PREFIXES):
        return 'speed'
    if (name in ('extruder', 'heater_bed') or
            name.startswith('extruder') and name[8:].isdigit() or
            name.startswith('heater_generic ')):
        return 'power'
    if name.startswith(OUTPUT_PREFIXES):
        return 'value'
    return None


def usage_metrics(objects):
    """Stable bounded selection; excess supported objects are reported explicitly.

    Standard legacy counters take priority, then exact Klipper object names.
    Called only during READY inventory/bootstrap, never in a sampling loop.
    """
    names = sorted({name for name in objects if usage_field(name)},
                   key=lambda n: (n not in ('fan', 'extruder', 'heater_bed'), n))
    metrics = tuple(UsageMetric(name, usage_field(name))
                    for name in names[:MAX_TRACKED_METRICS])
    return metrics, max(0, len(names) - len(metrics))
