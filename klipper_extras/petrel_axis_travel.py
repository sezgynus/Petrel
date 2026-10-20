"""Optional commanded Cartesian travel totals. No motion hooks or disk I/O.

Reads Klipper's existing trapq history with its existing C helper. Each tick
processes at most 128 records; overload drops that interval, never catches up
in an unbounded loop. These are recorded lower bounds, not encoder odometry.
"""
import logging
import math
import uuid
import chelper

INTERVAL = 0.1
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
        self.sensor_events = SensorEvents(self.printer)
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
            try:
                self.last_time = self.mcu.estimated_print_time(self.reactor.monotonic())
            except Exception:
                self.state = 'unavailable'
                if hasattr(self,'timer'):
                    self.reactor.update_timer(self.timer,self.reactor.NEVER)
                logging.exception('Petrel axis travel paused after homing')

    def _ready(self):
        self.sensor_events.ready()
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
        self.sensor_events.stop()
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
                    coverage='recorded_lower_bound', **self.sensor_events.status())


# Event capture uses Klipper's existing callback delivery. It adds no MCU
# configuration, pin registration, periodic reader, G-code, thread or disk I/O.
SENSOR_LIMIT = 64
COUNT_LIMIT = 2**53-1


class SensorEvents:
    def __init__(self, printer):
        self.printer = printer
        self.counts = {}
        self.kinds = {}
        self.excluded = 0
        self.state = 'starting'
        self._endstops = {}
        self._moves = {}
        self._disabled = set()
        self._ready_done = False
        printer.register_event_handler('homing:homing_move_begin', self.begin)
        printer.register_event_handler('homing:homing_move_end', self.end)
        printer.register_event_handler('gcode:command_error', self._clear_moves)

    def _add(self, name, kind):
        if not isinstance(name, str) or not 0 < len(name.encode('utf-8')) <= 96:
            self.excluded += 1
            return False
        if name in self.counts:
            return self.kinds[name] == kind
        if len(self.counts) >= SENSOR_LIMIT:
            self.excluded += 1
            return False
        self.counts[name] = 0
        self.kinds[name] = kind
        return True

    def _increment(self, name):
        # Optional accounting may never escape into the original callback.
        try:
            if self.state != 'tracking' or name in self._disabled:
                return
            value = self.counts[name]
            if value >= COUNT_LIMIT:
                self._disabled.add(name)
                return
            self.counts[name] = value+1
        except Exception:
            self._disabled.add(name)

    def _edge_callback(self, original, name, initial):
        previous = initial
        def callback(eventtime, value):
            nonlocal previous
            # Invoke Klipper's original exactly once, preserving its return
            # value and every exception. Accounting performs no callbacks.
            result = original(eventtime, value)
            try:
                current = bool(value) if type(value) in (bool, int) and value in (0, 1) else None
                if previous is False and current is True:
                    self._increment(name)
                previous = current
            except Exception:
                self._disabled.add(name)
            return result
        return callback

    def _button_groups(self, objects):
        # MCU_buttons retains only the last <=8-pin group in PrinterButtons.
        # Older groups remain owned by the MCU config-callback registry.
        # Support both old MCU and current MCUConfig helper layouts.
        groups = {}
        buttons = self.printer.lookup_object('buttons', None)
        if buttons is not None:
            for group in getattr(buttons, 'mcu_buttons', {}).values():
                groups[id(group)] = group
        for name, obj in objects:
            if name == 'mcu' or name.startswith('mcu '):
                helper = getattr(obj, '_config_helper', obj)
                for cb in getattr(helper, '_config_callbacks', ()):
                    group = getattr(cb, '__self__', None)
                    if (group is not None and isinstance(getattr(group, 'callbacks', None), list)
                            and isinstance(getattr(group, 'pin_list', None), list)):
                        groups[id(group)] = group
        return tuple(groups.values()), buttons

    def _attach_button(self, callback, names):
        # Debounced digital/ADC buttons point at DebounceButton.button_handler.
        # Its button_action is the existing bound sensor/button handler.
        owner = getattr(callback, '__self__', None)
        action = getattr(owner, 'button_action', None)
        target = getattr(action, '__self__', None)
        name = names.get(id(target))
        if name and name.startswith(('filament_switch_sensor ', 'gcode_button ')):
            if self._add(name, 'switch_activation'):
                initial = getattr(owner, 'logical_state', None)
                initial = bool(initial) if type(initial) in (bool, int) and initial in (0, 1) else None
                owner.button_action = self._edge_callback(action, name, initial)
            return callback
        # Older Klipper releases register handlers directly without DebounceButton.
        target = owner
        name = names.get(id(target))
        if name and name.startswith(('filament_switch_sensor ', 'gcode_button ')):
            if self._add(name, 'switch_activation'):
                helper = getattr(target, 'runout_helper', None)
                initial = (getattr(helper, 'filament_present', None) if helper is not None
                           else getattr(target, 'last_state', None))
                initial = bool(initial) if type(initial) in (bool, int) and initial in (0, 1) else None
                return self._edge_callback(callback, name, initial)
        if name and name.startswith('filament_motion_sensor '):
            if self._add(name, 'encoder_rising_edge'):
                # Baseline the first delivered physical level; never count a
                # startup-active pin as an encoder pulse.
                return self._edge_callback(callback, name, None)
        return callback

    def ready(self):
        if self._ready_done:
            return
        self._ready_done = True
        try:
            objects = tuple(self.printer.lookup_objects())
            names = {id(obj): name for name, obj in objects if
                     name.startswith(('filament_switch_sensor ',
                                      'filament_motion_sensor ', 'gcode_button '))}
            groups, buttons = self._button_groups(objects)
            for group in groups:
                callbacks = group.callbacks
                for index, item in enumerate(tuple(callbacks)):
                    if isinstance(item, tuple) and len(item) == 3 and callable(item[2]):
                        mask, shift, callback = item
                        callbacks[index] = (mask, shift, self._attach_button(callback, names))
            if buttons is not None:
                for group in getattr(buttons, 'adc_buttons', {}).values():
                    for index, item in enumerate(tuple(group.buttons)):
                        if isinstance(item, tuple) and len(item) == 3 and callable(item[2]):
                            lo, hi, callback = item
                            group.buttons[index] = (lo, hi, self._attach_button(callback, names))
            self.excluded += sum(1 for name in names.values() if name not in self.counts)
            # Registered physical endstops provide exact runtime identities.
            query = self.printer.lookup_object('query_endstops', None)
            configfile = self.printer.lookup_object('configfile', None)
            config = configfile.get_status(0.).get('settings', {}) if configfile else {}
            for endstop, name in getattr(query, 'endstops', ()):
                cfg = config.get(name, {})
                pin = cfg.get('endstop_pin') if isinstance(cfg, dict) else None
                if isinstance(pin, str) and pin and 'virtual_endstop' not in pin:
                    device = 'endstop '+name
                    if self._add(device, 'homing_contact'):
                        self._endstops[id(endstop)] = device
            # Contact probes use the same homing path. Eddy scans and other
            # non-contact measurements are deliberately not switch activations.
            probe = self.printer.lookup_object('probe', None)
            candidate = getattr(probe, 'mcu_probe', None)
            if candidate is not None:
                helper = getattr(candidate, 'homing_helper', None)
                physical = getattr(helper, 'mcu_probe', candidate)
                if callable(getattr(physical, 'home_start', None)) and callable(getattr(physical, 'home_wait', None)):
                    if self._add('probe', 'homing_contact'):
                        self._endstops[id(physical)] = 'probe'
            self.state = 'tracking'
        except Exception:
            # Already attached observers remain inert; original callbacks work.
            self.state = 'unavailable'
            logging.exception('Petrel sensor event capture unavailable')

    def _clear_moves(self, *args):
        for observations in self._moves.values():
            self._restore(observations)
        self._moves.clear()

    def begin(self, hmove):
        if self.state != 'tracking':
            return
        try:
            if len(self._moves) >= 4:
                self._clear_moves()
            observations = {}
            self._moves[id(hmove)] = observations
            for endstop, name in hmove.endstops[:SENSOR_LIMIT]:
                device = self._endstops.get(id(endstop))
                if device is None:
                    continue
                original_start = endstop.home_start
                original_wait = endstop.home_wait
                # Attach temporarily to the exact endstop used by this move.
                # A wrapper from an interrupted previous move is first restored.
                old = getattr(endstop, '_petrel_sensor_observer', None)
                if old is not None:
                    original_start, original_wait = old
                endstop._petrel_sensor_observer = (original_start, original_wait)
                slot = dict(device=device, name=name, endstop=endstop,
                            original=(original_start, original_wait), armed=False,
                            trigger_time=None)
                observations[id(endstop)] = slot
                def start(print_time, sample_time, sample_count, rest_time,
                          triggered=True, _slot=slot):
                    _slot['armed'] = False
                    result = _slot['original'][0](print_time, sample_time, sample_count,
                                                  rest_time, triggered=triggered)
                    _slot['armed'] = triggered is True
                    return result
                def wait(home_end_time, _slot=slot):
                    result = _slot['original'][1](home_end_time)
                    try:
                        if _slot['armed'] and type(result) in (int, float) and math.isfinite(result) and result > 0.:
                            _slot['trigger_time'] = result
                    except Exception:
                        pass
                    _slot['armed'] = False
                    return result
                endstop.home_start, endstop.home_wait = start, wait
        except Exception:
            self._restore(self._moves.pop(id(hmove), {}))

    def _restore(self, observations):
        for slot in observations.values():
            try:
                endstop = slot['endstop']
                endstop.home_start, endstop.home_wait = slot['original']
                del endstop._petrel_sensor_observer
            except Exception:
                self._disabled.add(slot['device'])

    def end(self, hmove):
        observations = self._moves.pop(id(hmove), {})
        try:
            for slot in observations.values():
                moved = any(sp.endstop_name == slot['name'] and sp.start_pos != sp.trig_pos
                            for sp in hmove.stepper_positions)
                if slot['trigger_time'] is not None and moved:
                    self._increment(slot['device'])
        except Exception:
            pass  # Incompatible motion metadata cannot affect the printer.
        finally:
            self._restore(observations)

    def stop(self):
        self.state = 'paused'
        for observations in self._moves.values():
            self._restore(observations)
        self._moves.clear()

    def status(self):
        return dict(sensor_schema=1, sensor_state=self.state,
                    sensor_counts=dict(self.counts), sensor_kinds=dict(self.kinds),
                    sensor_disabled=tuple(sorted(self._disabled)),
                    sensor_excluded=self.excluded)


def load_config(config):
    return PetrelAxisTravel(config)
