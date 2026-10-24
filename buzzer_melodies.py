"""Central immutable buzzer score library: (frequency Hz, duration seconds).

A zero frequency is an explicit rest. User scores preserve the original M300
S/P values; playback belongs exclusively to buzzer_control.Player.
"""
from types import MappingProxyType


def _score(*notes):
    return tuple((frequency, milliseconds / 1000.)
                 for frequency, milliseconds in notes)


MELODIES = MappingProxyType({
    'PRINT_DONE': _score((1319,150),(1568,150),(1760,150),(2093,300),(0,150),(2093,300)),
    'HEATING_DONE': _score((784,150),(988,150),(1319,200),(1760,200),(1568,200),(1976,400)),
    'COOLING_DONE': _score((2093,150),(1760,150),(1319,250),(988,300),(784,300),(523,400)),
    'ERROR': _score((1046,200),(784,200),(523,200),(0,100),(523,250),(494,300),(440,400)),
    'FILAMENT_OUT': _score((1568,150),(0,50),(1568,150),(0,50),(880,200),(988,250),(784,300)),
    'BOOT': _score((880,120),(1175,120),(1568,120),(2093,200),(2637,200),(3136,250),(4186,400)),
    'SHUTDOWN': _score((2093,200),(1760,200),(1319,200),(988,250),(784,400),(523,400)),
    'PAUSE': _score((1568,150),(1175,150),(880,300),(0,100),(880,250),(1319,250)),
    'RESUME': _score((784,150),(1046,150),(1319,200),(1760,250),(2093,300)),
    'LAYER_CHANGE': _score((2093,100),(0,40),(2349,120),(0,40),(2637,150),(0,40),(3136,180)),
    'HOMING': _score((1046,150),(1175,150),(1319,150),(1568,250),(1760,250)),
    'PROBE_SUCCESS': _score((988,150),(1175,150),(1568,150),(2093,250),(2637,250)),
    'PROBE_FAIL': _score((2093,120),(1976,120),(1760,150),(1319,250),(988,400)),
    'WARNING': _score((1175,150),(1175,150),(1175,150),(0,100),(784,250),(880,400)),
    'CUSTOM_EVENT': _score((987,150),(740,150),(987,150),(1319,200),(1760,300),(2093,400)),
    'OFF': (),
    'TICK': ((1800, .015),),
    'SHORT_BEEP': ((1400, .055),),
    'LOW': ((700, .055),),
    'HIGH': ((2400, .04),),
    'DOUBLE': ((1600, .035), (0, .035), (2000, .035)),
    'EMERGENCY': ((2200, .12), (1000, .12), (2200, .12),
                  (1000, .12), (2200, .12), (1000, .30),
                  (0, .09), (2600, .13), (0, .07), (2600, .28)),
})

# Stable UI preference indexes and compatibility exports; scores live above only.
TONE_NAMES = ('OFF', 'TICK', 'SHORT_BEEP', 'LOW', 'HIGH', 'DOUBLE')
PATTERNS = tuple(MELODIES[name] for name in TONE_NAMES)
EMERGENCY_PATTERN = MELODIES['EMERGENCY']


def get_melody(name):
    """Return an immutable score, rejecting unknown names before queuing audio."""
    if not isinstance(name, str) or name not in MELODIES:
        raise ValueError('Unknown buzzer melody: %r' % (name,))
    return MELODIES[name]
