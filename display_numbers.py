"""Mainsail numeric presentation policies; no telemetry or command mutation."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
import math


def js_round(value):
    value = float(value)
    low = math.floor(value)
    return low + (value-low >= .5)


def fixed(value, digits=0):
    """JS toFixed for the bounded finite numeric domains displayed by Petrel.

    Quantize the binary float itself, not its shortened decimal spelling.
    """
    with localcontext() as context:
        context.prec = 350
        number = Decimal.from_float(float(value))
        number = number.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
        if float(value)==0:
            number = abs(number)
        return format(number, '.%df'%digits)


def fit_decimal(value, cells, maximum_decimals=3):
    """Highest fitting precision, without trailing zeros or a negative zero."""
    for digits in range(maximum_decimals,-1,-1):
        text = fixed(value,digits)
        if digits:
            text = text.rstrip('0').rstrip('.')
        if text == '-0':
            text = '0'
        if len(text)<=cells:
            return text
    return '#' * cells


def compact(value):
    if not value:
        return '0'
    text = str(float(value))
    return text[:-2] if text.endswith('.0') else text


def cut(value, digits=0):
    return math.floor(float(value)*10**digits)/10**digits


def setting_text(setting, value):
    key = setting.key
    if key in ('speed','flow','fan','cruise'):
        text = str(js_round(value))
    elif key == 'scv':
        text = compact(cut(value,1))
    elif key.startswith(('pa@','smooth@')):
        text = compact(cut(value,3))
    elif key in ('retract_length','unretract_extra_length'):
        text = compact(cut(value,2))
    elif key in ('retract_speed','unretract_speed'):
        text = str(math.trunc(value))
    elif key == 'z':
        cells = max(1,(260-18-len(setting.label)*8-8)//8-len(setting.unit))
        text = fit_decimal(value,cells)
    elif key.startswith('nozzle@') or key == 'bed':
        text = compact(value)
    else:
        text = fixed(value,setting.decimals)
    text += setting.unit
    # Preserve the established row when an unusual external value would overlap
    # its label. Do not move labels, shrink fonts or truncate new precision.
    available = max(0,(260-18-len(setting.label)*8-8)//8)
    if len(text)<=available:
        return text
    legacy = ('%.*f'%(setting.decimals,value))+setting.unit
    return legacy if len(legacy)<=available else '#' * available


def motion_text(field,value):
    if field in ('max_velocity','max_accel'):
        return str(math.trunc(value))
    if field == 'square_corner_velocity':
        return compact(cut(value,1))
    if field == 'minimum_cruise_ratio':
        return str(js_round(value*100))+'%'
    return compact(value)


def clock_duration(seconds, max_chars=11):
    if seconds is None:
        return '--:--'
    total = max(0,int(seconds))
    hours, rest = divmod(total,3600)
    minutes, second = divmod(rest,60)
    text = '%d:%02d:%02d'%(hours,minutes,second)
    return text if len(text)<=max_chars else '%02d:%02d'%(hours,minutes)
