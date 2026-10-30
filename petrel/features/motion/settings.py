"""Klipper runtime motion parameters and their documented numeric domains."""
import math

# status field, G-code argument, menu label, encoder increment
PARAMETERS = (
    ('max_velocity', 'VELOCITY', 'Velocity mm/s', 1),
    ('max_accel', 'ACCEL', 'Accel mm/s2', 10),
    ('square_corner_velocity', 'SQUARE_CORNER_VELOCITY', 'SCV mm/s', .1),
    ('minimum_cruise_ratio', 'MINIMUM_CRUISE_RATIO', 'Cruise ratio', .01),
)


def validate(field, value):
    if field not in {item[0] for item in PARAMETERS}:
        raise ValueError('Unknown motion setting')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Motion setting must be finite')
    if field in ('max_velocity', 'max_accel') and value <= 0:
        raise ValueError('Velocity and acceleration must be positive')
    if field == 'square_corner_velocity' and value < 0:
        raise ValueError('SCV must be nonnegative')
    if field == 'minimum_cruise_ratio' and not 0 <= value < 1:
        raise ValueError('Cruise ratio must be at least zero and below one')
    return value
