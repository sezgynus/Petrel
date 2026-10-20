"""Small passive usage contracts, independent of actuator/test permissions.

Sources: Klipper Status Reference (fan, heater, output_pin, pwm_cycle_time).
An object-list entry establishes the documented field contract; each runtime
sample must still validate the value. No source state/configuration is retained.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

MAX_TRACKED_METRICS = 64
MAX_DEVICE_NAME = 96  # UTF-8 bytes, also bounds JSON escape expansion.
MAX_LED_CHAIN = 64
MAX_TRACKED_LEDS = 256
LED_PREFIXES = ('led ', 'neopixel ', 'dotstar ', 'pca9533 ', 'pca9632 ')
FAN_PREFIXES = ('fan_generic ', 'heater_fan ', 'controller_fan ', 'temperature_fan ')
OUTPUT_PREFIXES = ('output_pin ', 'pwm_cycle_time ', 'pwm_tool ')


@dataclass(frozen=True, slots=True)
class UsageMetric:
    device: str
    field: str
    metric_id: str = 'sampled_on_s'
    unit: str = 's'
    elements: int = 0

    def active(self, status):
        """None means unreadable, not OFF; booleans/NaN/negative fail closed."""
        values = status.get(self.device)
        value = values.get(self.field) if isinstance(values, Mapping) else None
        if self.field=='color_data':
            if not isinstance(value,(tuple,list)) or len(value)!=self.elements:
                return None
            active=False
            for color in value:
                if not isinstance(color,(tuple,list)) or len(color)!=4:
                    return None
                for channel in color:
                    if not numeric(channel) or channel>1:
                        return None
                    active = active or channel>0
            return active
        if not numeric(value) or (self.field in ('speed','power') and value>1):
            return None
        return value > 0


def usage_field(name):
    """Only documented object classes; never infer a source from a pin key."""
    if not isinstance(name, str) or not name:
        return None
    if name == 'fan' or name.startswith(FAN_PREFIXES):
        return 'speed'
    if (name in ('extruder', 'heater_bed') or
            name.startswith('extruder') and name[8:].isdigit() or
            name.startswith('heater_generic ')):
        return 'power'
    if name.startswith(OUTPUT_PREFIXES):
        return 'value'
    if name.startswith(LED_PREFIXES):
        return 'color_data'
    return None


def usage_metrics(objects,settings=None):
    """Stable bounded selection; excess supported objects are reported explicitly.

    Standard legacy counters take priority, then exact Klipper object names.
    Called only during READY inventory/bootstrap, never in a sampling loop.
    """
    names = sorted({name for name in objects if usage_field(name)},
                   key=lambda n: (n not in ('fan', 'extruder', 'heater_bed'), n))
    metrics=[]
    pixels=0
    for name in names:
        if len(metrics)>=MAX_TRACKED_METRICS or len(name.encode('utf-8'))>MAX_DEVICE_NAME:
            continue
        field=usage_field(name)
        count=0
        if field=='color_data':
            cfg=settings.get(name,{}) if isinstance(settings,Mapping) else {}
            count=cfg.get('chain_count',1) if isinstance(cfg,Mapping) else 1
            if (type(count) is not int or not 1<=count<=MAX_LED_CHAIN
                    or pixels+count>MAX_TRACKED_LEDS):
                continue
            pixels+=count
        metrics.append(UsageMetric(name,field,elements=count))
    return tuple(metrics), len(names)-len(metrics)


def metric_counter(usage, device, metric_id):
    """Resolve global/device metrics without exposing recorder implementation.

    Older providers omit availability; new providers distinguish missing live
    samples from the durable (still valid) accumulated lower bound.
    """
    available = usage.get('available_metrics')
    if available is not None and (device, metric_id) not in available:
        if metric_id != 'sampled_print_s' or (None, metric_id) not in available:
            return None
    bucket = usage.get(metric_id)
    value = bucket.get(device) if isinstance(bucket, Mapping) else bucket
    return value if numeric(value) else None


def numeric(value):
    if type(value) not in (int,float) or value<0:
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False
