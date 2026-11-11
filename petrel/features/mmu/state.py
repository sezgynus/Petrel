"""Immutable Happy Hare state, units, LEDs and telemetry normalization.

Gate indices stay zero based in commands and LCD labels, matching Happy Hare.
Missing telemetry remains unknown and never enables a motion operation.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import math


def integer(value, default=None):
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def boolean(value):
    return value if isinstance(value, bool) else None


def switch(value):
    if isinstance(value, bool):
        return value
    return bool(value) if integer(value) in (0, 1) else None


def text(value, default='Unknown'):
    return value if isinstance(value, str) and value else default


def number(value, default=None):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else default


@dataclass(frozen=True)
class MMUUnit:
    name: str
    first_gate: int
    num_gates: int
    selector_type: str
    always_gripped: bool | None
    config_name: str = ''


def units_from_snapshot(snapshot, gates):
    raw = snapshot.get('status', {}).get('mmu_machine')
    if not isinstance(raw, Mapping):
        return ()
    count = integer(raw.get('num_units'))
    if count is None or not 1 <= count <= gates or integer(raw.get('num_gates')) != gates:
        return ()
    units, first = [], 0
    for i in range(count):
        unit = raw.get('unit_%d' % i)
        if not isinstance(unit, Mapping):
            return ()
        n = integer(unit.get('num_gates'))
        if integer(unit.get('first_gate')) != first or n is None or n <= 0 or first + n > gates:
            return ()
        units.append(MMUUnit(text(unit.get('display_name'), text(unit.get('name'), 'Unit %d' % (i + 1))),
                             first, n, text(unit.get('selector_type')), boolean(unit.get('filament_always_gripped')),
                             text(unit.get('name'), '')))
        first += n
    return tuple(units) if first == gates else ()


def motor_states(snapshot, units):
    settings = snapshot.get('settings', {})
    driver_status = snapshot.get('status', {}).get('stepper_enable', {})
    drivers = driver_status.get('steppers', {}) if isinstance(driver_status, Mapping) else {}
    if not isinstance(settings, Mapping) or not isinstance(drivers, Mapping) or not units:
        return ()
    names = set()
    for unit in units:
        config = settings.get('mmu_unit ' + unit.config_name)
        if not isinstance(config, Mapping):
            return ()
        gears = config.get('gear_steppers', config.get('gear_stepper'))
        if isinstance(gears, str):
            gears = [v.strip() for v in gears.split(',')]
        if (not isinstance(gears, (tuple, list)) or not gears
                or any(not isinstance(v, str) or not v or any(c.isspace() for c in v) for v in gears)):
            return ()
        names.update('mmu_stepper ' + v for v in gears)
        if unit.selector_type in {'LinearSelector', 'LinearServoSelector', 'LinearMGSelector',
                                  'LinearMGServoSelector', 'RotarySelector', 'IndexedSelector'}:
            selector = config.get('selector_stepper')
            if not isinstance(selector, str) or not selector or any(c.isspace() for c in selector):
                return ()
            names.add('mmu_stepper ' + selector)
        elif unit.selector_type not in {'ServoSelector', 'VirtualSelector'}:
            return ()
    return tuple((name, boolean(drivers.get(name))) for name in sorted(names))


@dataclass(frozen=True)
class MMULeds:
    object_name: str
    enabled: bool | None
    animation: bool | None
    exit_effect: str
    segments: tuple


def led_state(snapshot, units, unit_index):
    if unit_index is None or not 0 <= unit_index < len(units):
        return None
    unit = units[unit_index]
    name = 'mmu_leds ' + unit.config_name
    raw = snapshot.get('status', {}).get(name)
    if not isinstance(raw, Mapping) or integer(raw.get('num_gates')) != unit.num_gates:
        return None
    counts = tuple(integer(raw.get(k)) for k in ('exit', 'entry', 'status', 'logo'))
    if any(n is None or n < 0 for n in counts) or not any(counts):
        return None
    return MMULeds(name, switch(raw.get('enabled')), switch(raw.get('animation')),
                   text(raw.get('exit_effect')), counts)


@dataclass(frozen=True)
class MMUState:
    epoch: int
    num_gates: int
    gate: int | None
    tool: int | None
    enabled: bool | None
    action: str
    print_state: str
    filament: str
    locked: bool | None
    gate_status: tuple
    ttg_map: tuple
    materials: tuple
    names: tuple
    temperatures: tuple
    spool_ids: tuple
    sensors: tuple
    sync_drive: bool | None
    bowden_progress: int | None
    reason: str
    spoolman_support: str
    endless_enabled: bool | None
    endless_groups: tuple
    colors: tuple
    units: tuple
    unit: int | None
    homed: bool | None
    grip: bool | None
    motors: tuple
    leds: MMULeds | None
    filament_pos: int | None = None
    filament_position: float | None = None
    filament_direction: int | None = None
    filament_remaining: float = 0
    filament_remaining_color: str = ''
    gate_homing_endstop: str = ''
    extruder_homing_endstop: str = ''
    extruder_force_homing: bool = False

    @classmethod
    def from_snapshot(cls, snapshot):
        if snapshot.get('state') != 'ready':
            return None
        raw = snapshot.get('status', {}).get('mmu')
        if not isinstance(raw, Mapping):
            return None
        count = integer(raw.get('num_gates'))
        if count is None or not 1 <= count <= 256:
            return None
        def values(key, parse):
            seq = raw.get(key, ())
            if not isinstance(seq, (tuple, list)):
                seq = ()
            return tuple(parse(seq[i]) if i < len(seq) else None for i in range(count))
        def index(value):
            n = integer(value)
            return n if n is not None and -2 <= n < count else None
        status = text(raw.get('print_state'))
        known_states = {'initialized', 'ready', 'started', 'printing', 'complete',
                        'cancelled', 'error', 'pause_locked', 'paused', 'standby', 'idle'}
        locked = (status == 'pause_locked' if status in known_states
                  else boolean(raw.get('is_locked')))
        filament = text(raw.get('filament')).lower()
        if filament not in ('loaded', 'unloaded'):
            filament = 'unknown'
        # Never promote an intermediate/contradictory physical state to loaded/empty.
        pos = integer(raw.get('filament_pos'))
        if 'filament_pos' in raw and pos != {'loaded': 10, 'unloaded': 0}.get(filament):
            filament = 'unknown'
        progress = raw.get('bowden_progress')
        if (isinstance(progress, bool) or not isinstance(progress, (int, float))
                or not math.isfinite(progress) or not 0 <= progress <= 100):
            progress = None
        else:
            progress = round(progress)
        sensors = raw.get('sensors', {})
        if not isinstance(sensors, Mapping):
            sensors = {}
        selector = raw.get('selector', {})
        selector = selector if isinstance(selector, Mapping) else {}
        grip = {'Gripped': True, 'Released': False}.get(text(selector.get('grip')))
        if grip is None:
            grip = {'Down': True, 'Up': False}.get(text(selector.get('servo')))
        units = units_from_snapshot(snapshot, count)
        saved = snapshot.get('status', {}).get('save_variables', {})
        variables = saved.get('variables', {}) if isinstance(saved, Mapping) else {}
        variables = variables if isinstance(variables, Mapping) else {}
        config = snapshot.get('settings', {}).get('mmu', {})
        config = config if isinstance(config, Mapping) else {}
        remaining = max(0, number(raw.get('filament_remaining', variables.get('mmu_state_filament_remaining')), 0))
        remaining_color = text(raw.get('filament_remaining_color', variables.get('mmu_state_filament_remaining_color')), '')
        return cls(snapshot.get('epoch', 0), count, index(raw.get('gate')),
                   index(raw.get('tool')), boolean(raw.get('enabled')),
                   text(raw.get('action')), status, filament, locked,
                   values('gate_status', lambda v: integer(v) if integer(v) in (-1, 0, 1, 2) else None),
                   values('ttg_map', index), values('gate_material', lambda v: text(v, '--')),
                   values('gate_filament_name', lambda v: text(v, '--')),
                   values('gate_temperature', lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None),
                   values('gate_spool_id', integer),
                   tuple(sorted((str(k), boolean(v)) for k, v in sensors.items())),
                   boolean(raw.get('sync_drive')), progress,
                   text(raw.get('reason_for_pause'), ''), text(raw.get('spoolman_support')),
                   switch(raw.get('endless_spool_enabled', raw.get('endless_spool'))),
                   values('endless_spool_groups', lambda v: integer(v) if integer(v) is not None and v >= 0 else None),
                   values('gate_color', lambda v: text(v, '--')), units,
                   integer(raw.get('unit')), boolean(raw.get('is_homed')), grip, motor_states(snapshot, units),
                   led_state(snapshot, units, integer(raw.get('unit'))),
                   pos if pos is not None and -1 <= pos <= 10 else None,
                   number(raw.get('filament_position')), integer(raw.get('filament_direction')),
                   remaining, remaining_color,
                   text(config.get('gate_homing_endstop'), ''),
                   text(config.get('extruder_homing_endstop'), ''),
                   switch(config.get('extruder_force_homing')) is True)

    @property
    def busy(self):
        return self.action.lower() != 'idle'

    @property
    def fingerprint(self):
        return (self.epoch, self.num_gates, self.gate, self.tool, self.enabled,
                self.action, self.print_state, self.filament, self.locked,
                self.gate_status, self.ttg_map, self.endless_enabled, self.endless_groups,
                self.materials, self.colors, self.spool_ids, self.spoolman_support,
                self.temperatures, self.units, self.unit, self.homed, self.grip, self.sync_drive, self.motors, self.leds)

    @property
    def active_unit(self):
        return self.units[self.unit] if self.unit is not None and 0 <= self.unit < len(self.units) else None

    def tools_for_gate(self, gate):
        return tuple(i for i, mapped in enumerate(self.ttg_map) if mapped == gate)

    def sensor(self, name):
        sensors = dict(self.sensors)
        aliases = {'mmu_gate': 'mmu_shared_exit', 'mmu_pre_gate': 'mmu_entry', 'mmu_gear': 'mmu_exit'}
        return sensors.get(name, sensors.get(aliases.get(name)))
