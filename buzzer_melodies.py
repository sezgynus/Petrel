"""Central immutable buzzer score library: (frequency Hz, duration seconds).

A zero frequency is an explicit rest. Short event
motifs (v2) are defined here; playback belongs exclusively to buzzer_control.Player.
"""
from types import MappingProxyType


def _score(*notes):
    return tuple((frequency, milliseconds / 1000.)
                 for frequency, milliseconds in notes)


MELODIES = MappingProxyType({
    'PRINT_DONE': _score((784,90),(0,25),(1047,90),(0,25),(1319,90),(0,35),(1568,160),(0,60),(1047,260)),
    'HEATING_DONE': _score((659,90),(0,25),(784,90),(0,25),(1047,220)),
    'COOLING_DONE': _score((1319,110),(0,30),(1047,110),(0,30),(784,140),(0,40),(659,220)),
    'ERROR': _score((988,110),(0,35),(698,180),(0,130),(988,110),(0,35),(698,280)),
    'FILAMENT_OUT': _score((1175,90),(0,70),(1175,90),(0,70),(1175,90),(0,140),(784,260)),
    'BOOT': _score((523,70),(0,20),(659,70),(0,20),(784,100),(0,30),(1047,150),(0,30),(1319,200)),
    'SHUTDOWN': _score((1047,100),(0,30),(784,120),(0,30),(659,140),(0,40),(523,260)),
    'PAUSE': _score((784,100),(0,30),(659,170),(0,130),(659,100)),
    'RESUME': _score((659,80),(0,25),(784,100),(0,25),(1047,240)),
    'LAYER_CHANGE': _score((1319,45),(0,25),(1568,65)),
    'HOMING': _score((523,70),(0,35),(784,90),(0,120),(523,70),(0,35),(784,150)),
    'PROBE_SUCCESS': _score((1047,70),(0,30),(1319,180)),
    'PROBE_FAIL': _score((784,100),(0,40),(523,160),(0,100),(523,180)),
    'WARNING': _score((880,120),(0,100),(880,120),(0,100),(659,180)),
    'CUSTOM_EVENT': _score((784,80),(0,35),(1319,120),(0,35),(1047,220)),
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
