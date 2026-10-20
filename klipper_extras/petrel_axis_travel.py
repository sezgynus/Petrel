"""Optional commanded Cartesian travel totals. No motion hooks or disk I/O.

Reads Klipper's existing trapq history with its existing C helper. Each tick
processes at most 128 records; overload drops that interval, never catches up
in an unbounded loop. These are recorded lower bounds, not encoder odometry.
"""
import logging
import math
import uuid
import chelper

INTERVAL = 0.5
CAPACITY = 128


def distances(move, start, end):
    """Integrate only the elapsed portion; no coordinate-offset subtraction."""
    lo = max(0., start - move.print_time)
    hi = min(move.move_t, end - move.print_time)
    if hi <= lo:
        return (0., 0., 0.)
    distance = (hi-lo) * (move.start_v + .5*move.accel*(hi+lo))
    return tuple(abs(r*distance) for r in (move.x_r, move.y_r, move.z_r))


class PetrelAxisTravel:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.session_id = uuid.uuid4().hex
        self.totals = [0., 0., 0.]
        self.dropped_batches = 0
        self.state = 'starting'
        self.last_time = None
        self.homing = 0
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('klippy:shutdown', self._stop)
        self.printer.register_event_handler('klippy:disconnect', self._stop)
        self.printer.register_event_handler('homing:homing_move_begin', self._homing_begin)
        self.printer.register_event_handler('homing:homing_move_end', self._homing_end)

    def _homing_begin(self, *args):
        self.homing += 1
        self.dropped_batches += 1

    def _homing_end(self, *args):
        self.homing = max(0, self.homing-1)
        if hasattr(self, 'mcu'):
            self.last_time = self.mcu.estimated_print_time(self.reactor.monotonic())

    def _ready(self):
        try:
            self.mcu = self.printer.lookup_object('mcu')
            self.trapq = self.printer.lookup_object('toolhead').get_trapq()
            ffi, self.lib = chelper.get_ffi()
            self.buffer = ffi.new('struct pull_move[%d]' % CAPACITY)
            self.last_time = self.mcu.estimated_print_time(self.reactor.monotonic())
            self.state = 'tracking'
            self.timer = self.reactor.register_timer(self._tick,
                                                     self.reactor.monotonic()+INTERVAL)
        except Exception:
            self.state = 'unavailable'
            logging.exception('Petrel axis travel unavailable; motion is unchanged')

    def _stop(self):
        self.state = 'paused'
        if hasattr(self, 'timer'):
            self.reactor.update_timer(self.timer, self.reactor.NEVER)

    def _tick(self, eventtime):
        try:
            end = self.mcu.estimated_print_time(eventtime)
            start = self.last_time
            # History retention differs between Klipper versions. Do not try
            # to recover long stalls or clock resets from a partial history.
            if self.homing:
                pass  # Endstop/probe-triggered queue truncation is excluded.
            elif end < start or end-start > 2.:
                self.dropped_batches += 1
            elif end > start:
                count = self.lib.trapq_extract_old(self.trapq, self.buffer,
                                                  CAPACITY, start, end)
                if count >= CAPACITY:
                    self.dropped_batches += 1
                else:
                    delta = [0., 0., 0.]
                    for index in range(count):
                        values = distances(self.buffer[index], start, end)
                        for axis in range(3):
                            delta[axis] += values[axis]
                    if not all(math.isfinite(v) and v >= 0. for v in delta):
                        raise ValueError('invalid travel delta')
                    totals = [a+b for a,b in zip(self.totals, delta)]
                    if not all(math.isfinite(v) for v in totals):
                        raise ValueError('invalid travel total')
                    self.totals = totals
            self.last_time = end
        except Exception:
            # Optional maintenance must never shut down or block printing.
            self.state = 'unavailable'
            logging.exception('Petrel axis travel stopped; motion is unchanged')
            return self.reactor.NEVER
        return eventtime + INTERVAL

    def get_status(self, eventtime):
        return dict(session_id=self.session_id, x_mm=self.totals[0],
                    y_mm=self.totals[1], z_mm=self.totals[2],
                    state=self.state, dropped_batches=self.dropped_batches,
                    coverage='recorded_lower_bound')


def load_config(config):
    return PetrelAxisTravel(config)
