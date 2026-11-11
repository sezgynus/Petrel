"""Guarded, completion-tracked Happy Hare operations."""
from collections.abc import Mapping
from dataclasses import dataclass, replace
import time
from petrel.features.mmu.state import MMUState, integer


@dataclass(frozen=True)
class MMUOperation:
    action: str
    gate: int | None
    tool: int | None
    loaded: bool | None
    fingerprint: tuple
    script: str
    label: str
    values: tuple = ()
    enabled: bool | None = None
    expected_spool_ids: tuple = ()

class MMUSession:
    TIMEOUT = 300.0
    GATE_ACTIONS = {'select', 'load', 'change', 'unload', 'eject', 'preload', 'check'}
    RECOVERY_ACTIONS = {'recover', 'manual', 'unlock', 'resume'}
    GRIP_SELECTORS = {'ServoSelector', 'RotarySelector', 'LinearServoSelector', 'LinearMGServoSelector'}
    HOME_SELECTORS = {'LinearSelector', 'LinearServoSelector', 'LinearMGSelector', 'LinearMGServoSelector'}
    LED_MODES = ('off', 'gate_status', 'filament_color', 'slicer_color')

    def __init__(self, printer):
        self.printer = printer
        self.pending = None
        self.phase, self.message = 'idle', ''
        self.operation = None
        self._cursor = None

    @property
    def state(self):
        return MMUState.from_snapshot(self.printer.subscription.snapshot())

    def prepare(self, action, gate=None, tool=None, loaded=None, snapshot=None, ignore_pending=False, values=(), enabled=None, parsed_state=None):
        p = self.printer
        expected_spool_ids = ()
        snap = p.subscription.snapshot() if snapshot is None else snapshot
        m = parsed_state if parsed_state is not None else MMUState.from_snapshot(snap)
        if (p.connection_error or not p.state.ready or snap.get('epoch') != p.state.epoch
                or m is None):
            raise ValueError('MMU unavailable')
        if self.pending is not None and not ignore_pending:
            raise ValueError('Wait for MMU operation')
        if self.phase == 'error':
            raise ValueError('Acknowledge MMU result first')
        if m.enabled is not True and not (action == 'enable' and m.enabled is False and enabled is True):
            raise ValueError('MMU disabled or unknown')
        if m.busy or p.jog_recovery_required:
            raise ValueError('MMU busy or recovery needed')
        if snap.get('status', {}).get('manual_probe', {}).get('is_active') or any(
                getattr(getattr(p, name, None), 'pending', None)
                for name in ('bed_mesh', 'screws_tilt', 'probe_wizard')):
            raise ValueError('Another operation is active')
        ps = snap.get('status', {}).get('print_stats', {}).get('state')
        if ps not in ('standby', 'complete', 'cancelled', 'error', 'paused', 'printing'):
            raise ValueError('Print state unknown')
        if ps == 'printing' or m.print_state in ('started', 'printing'):
            raise ValueError('Printing; monitoring only')
        if action not in self.RECOVERY_ACTIONS:
            if ps == 'paused' or m.print_state in ('paused', 'pause_locked'):
                raise ValueError('Use recovery during a pause')
            if m.locked is not False:
                raise ValueError('MMU lock state unknown')
        elif m.locked is None:
            raise ValueError('MMU lock state unknown')
        if action in self.GATE_ACTIONS or action == 'spool':
            if integer(gate) is None or not 0 <= gate < m.num_gates:
                raise ValueError('Invalid gate')
            target = 'G%d' % gate
        else:
            target = ''
        if action in ('select', 'load', 'preload', 'check', 'bypass', 'home_selector', 'check_all', 'grip', 'release', 'enable', 'motors_off', 'unit_select') and m.filament != 'unloaded':
            raise ValueError('Unload filament first')
        if action in ('unload', 'unload_extruder') and not (
                m.filament == 'loaded' or m.filament_pos is not None and 1 <= m.filament_pos <= 9):
            raise ValueError('Known filament position required')
        if action == 'enable':
            if not isinstance(enabled, bool) or m.enabled == enabled:
                raise ValueError('Choose a different known MMU enable state')
            script, label = 'MMU ENABLE=%d' % enabled, 'Enable MMU' if enabled else 'Disable MMU'
        elif action == 'motors_off':
            if not m.motors or any(v is None for _, v in m.motors) or m.sync_drive is None:
                raise ValueError('Known MMU driver states required')
            values = tuple(name for name, _ in m.motors)
            script, label = 'MMU_MOTORS_OFF UNIT=ALL', 'Release all MMU motors'
        elif action == 'unit_select':
            if not isinstance(values, (tuple, list)) or not values or integer(values[0]) is None:
                raise ValueError('Choose a valid MMU unit')
            index = values[0]
            if len(m.units) < 2 or not 0 <= index < len(m.units):
                raise ValueError('Validated multiple units required')
            gate = m.units[index].first_gate
            values = (index, m.units)
            script = 'MMU_SELECT GATE=%d' % gate
            label = 'Select U%d / G%d' % (index + 1, gate)
        elif action in ('led_enable', 'led_animation', 'led_mode'):
            leds = m.leds
            if m.active_unit is None or leds is None or leds.enabled is None or leds.animation is None:
                raise ValueError('Known unit LED state required')
            mode = None
            if action == 'led_mode':
                if not isinstance(values, (tuple, list)) or not values or not isinstance(values[0], str) or values[0] not in self.LED_MODES:
                    raise ValueError('Unsupported LED exit mode')
                mode = values[0]
                if not leds.segments[0] or mode == leds.exit_effect:
                    raise ValueError('Choose a different supported exit mode')
                desired = replace(leds, exit_effect=mode)
                argument, label = 'EXIT_EFFECT=' + mode, 'Exit: ' + mode.replace('_', ' ')
            else:
                field = 'enabled' if action == 'led_enable' else 'animation'
                if not isinstance(enabled, bool) or getattr(leds, field) == enabled:
                    raise ValueError('Choose a different known LED state')
                desired = replace(leds, **{field: enabled})
                argument = ('ENABLE' if action == 'led_enable' else 'ANIMATION') + '=%d' % enabled
                label = ('LEDs ' if action == 'led_enable' else 'Animation ') + ('ON' if enabled else 'OFF')
            values = (mode, m.unit, m.units, desired)
            script = 'MMU_LED UNIT=%d %s' % (m.unit, argument)
            label = 'U%d ' % (m.unit + 1) + label
        elif action == 'select':
            script, label = 'MMU_SELECT GATE=%d' % gate, 'Select ' + target
        elif action == 'load':
            if gate != m.gate or m.gate_status[gate] not in (1, 2):
                raise ValueError('Select an available gate first')
            script, label = 'MMU_LOAD', 'Load ' + target
        elif action == 'change':
            tools = m.tools_for_gate(gate)
            if not tools or m.gate_status[gate] not in (1, 2) or m.filament == 'unknown' or m.gate == -2:
                raise ValueError('Mapped available gate required')
            if tool is not None and tool not in tools:
                raise ValueError('Tool mapping changed')
            tool = tool if tool is not None else m.tool if m.tool in tools else tools[0]
            script, label = 'MMU_CHANGE_TOOL TOOL=%d STANDALONE=1' % tool, 'Load/change T%d / %s' % (tool, target)
        elif action == 'unload':
            if gate != m.gate:
                raise ValueError('Unload the current gate')
            script, label = 'MMU_UNLOAD', 'Unload ' + target
        elif action == 'eject':
            if m.filament == 'unknown' or (m.filament == 'loaded' and gate != m.gate):
                raise ValueError('Unload current filament first')
            # FORCE explicitly ejects the spool after unloading the current gate.
            script, label = 'MMU_EJECT GATE=%d FORCE=1' % gate, 'Eject spool ' + target
        elif action in ('preload', 'check'):
            script = '%s GATE=%d' % ('MMU_PRELOAD' if action == 'preload' else 'MMU_CHECK_GATE', gate)
            label = action.title() + ' ' + target
        elif action == 'bypass':
            script, label = 'MMU_SELECT BYPASS=1', 'Select bypass'
        elif action in ('load_extruder', 'unload_extruder'):
            if m.gate != -2:
                raise ValueError('Select bypass first')
            if action == 'load_extruder' and m.filament != 'unloaded':
                raise ValueError('Unload filament first')
            script = ('MMU_LOAD' if action == 'load_extruder' else 'MMU_UNLOAD') + ' EXTRUDER_ONLY=1'
            label = action.replace('_', ' ').title()
        elif action == 'recover':
            script, label = 'MMU_RECOVER', 'Auto recover'
        elif action == 'manual':
            if integer(tool) is None or integer(gate) is None or not 0 <= tool < m.num_gates or not 0 <= gate < m.num_gates or not isinstance(loaded, bool):
                raise ValueError('Choose actual tool/gate/state')
            script = 'MMU_RECOVER TOOL=%d GATE=%d LOADED=%d' % (tool, gate, loaded)
            label = 'Set T%d / G%d %s' % (tool, gate, 'loaded' if loaded else 'unloaded')
        elif action == 'unlock':
            if m.locked is not True:
                raise ValueError('MMU is not locked')
            script, label = 'MMU_UNLOCK', 'Unlock / reheat'
        elif action == 'map':
            if (not isinstance(values, (tuple, list)) or len(values) != m.num_gates
                    or any(integer(v) is None or not 0 <= v < m.num_gates for v in values)
                    or any(v is None or v < 0 for v in m.ttg_map)):
                raise ValueError('Complete valid tool map required')
            values = tuple(values)
            script = 'MMU_TTG_MAP MAP=' + ','.join(str(v) for v in values)
            label = 'Save tool map'
        elif action == 'endless':
            if (not isinstance(enabled, bool) or m.endless_enabled is None
                    or any(v is None for v in m.endless_groups)
                    or not isinstance(values, (tuple, list)) or len(values) != m.num_gates
                    or any(integer(v) is None or v < 0 for v in values)):
                raise ValueError('Complete EndlessSpool state required')
            values = tuple(values)
            script = 'MMU_ENDLESS_SPOOL ENABLE=%d GROUPS=%s' % (enabled, ','.join(str(v) for v in values))
            label = 'Save EndlessSpool'
        elif action == 'spool':
            if m.spoolman_support not in ('off', 'readonly', 'push'):
                raise ValueError('Spoolman mode blocks local assignment')
            if (not isinstance(values, (tuple, list)) or len(values) not in (1, 5)
                    or integer(values[0]) is None or (values[0] != -1 and values[0] < 1)
                    or any(sid is None or (sid != -1 and sid < 1) for sid in m.spool_ids)):
                raise ValueError('Known spool IDs and valid assignment required')
            values = tuple(values)
            if len(values) == 5:
                sid, name, material, color, temperature = values
                if (sid < 1 or any(not isinstance(v, str) or
                        any(c in '\"\'' or not c.isprintable() for c in v)
                        for v in (name, material))
                        or not isinstance(color, str) or len(color) != 6
                        or any(c not in '0123456789abcdefABCDEF' for c in color)
                        or integer(temperature) is None or temperature < -1):
                    raise ValueError('Invalid Spoolman filament metadata')
                script = ('MMU_GATE_MAP GATE=%d SPOOLID=%d NAME="%s" '
                          'MATERIAL="%s" COLOR="%s" TEMP=%d QUIET=1'
                          % (gate, sid, name, material, color, temperature))
            else:
                temperature = m.temperatures[gate]
                if temperature is None or temperature <= 0 or int(temperature) != temperature:
                    raise ValueError('Known filament temperature required')
                temperature = int(temperature)
                script = 'MMU_GATE_MAP GATE=%d SPOOLID=%d TEMP=%d' % (gate, values[0], temperature)
            label = ('Clear spool on ' if values[0] == -1 else 'Assign #%d to ' % values[0]) + target
            expected_spool_ids = tuple(values[0] if i == gate else -1 if values[0] > 0 and sid == values[0] else sid
                                       for i, sid in enumerate(m.spool_ids))
        elif action == 'check_all':
            if m.gate is None or m.gate < 0:
                raise ValueError('Select an MMU gate first')
            script, label = 'MMU_CHECK_GATE ALL=1', 'Check all %d gates' % m.num_gates
        elif action == 'home_selector':
            unit = m.active_unit
            if len(m.units) != 1 or unit is None or unit.selector_type not in self.HOME_SELECTORS:
                raise ValueError('Single homing selector required')
            tools = [i for i, gate in enumerate(m.ttg_map) if gate is not None and gate >= 0]
            if not tools or any(gate is None or gate < 0 for gate in m.ttg_map):
                raise ValueError('Valid tool map required')
            tool = m.tool if m.tool in tools else tools[0]
            values = (m.units,)
            script, label = 'MMU_HOME UNIT=0 TOOL=%d' % tool, 'Home selector / T%d' % tool
        elif action in ('grip', 'release', 'sync_on', 'sync_off'):
            unit = m.active_unit
            if (unit is None or m.gate is None or not unit.first_gate <= m.gate < unit.first_gate + unit.num_gates):
                raise ValueError('Known active unit and gate required')
            if unit.selector_type in self.HOME_SELECTORS and m.homed is not True:
                raise ValueError('Home selector before drive operations')
            gate, values = m.gate, (m.unit, m.units)
            if action in ('grip', 'release'):
                if unit.selector_type not in self.GRIP_SELECTORS or m.grip is None:
                    raise ValueError('Grip-capable selector telemetry required')
                if action == 'release' and unit.always_gripped is not False:
                    raise ValueError('Selector cannot release filament')
                script = 'MMU_GRIP' if action == 'grip' else 'MMU_RELEASE'
                label = '%s G%d' % (action.title(), m.gate)
            else:
                if m.filament != 'loaded' or m.sync_drive is None or unit.always_gripped is None:
                    raise ValueError('Loaded filament and known sync state required')
                if action == 'sync_off' and unit.always_gripped:
                    raise ValueError('Always-gripped unit cannot unsync')
                script = 'MMU_SYNC_GEAR_MOTOR SYNC=%d' % (action == 'sync_on')
                label = 'Gear sync ' + ('ON' if action == 'sync_on' else 'OFF')
        elif action == 'resume':
            if ps != 'paused' or m.locked is not False or m.filament != 'loaded':
                raise ValueError('Recover and unlock first')
            script, label = 'RESUME', 'Resume print'
        else:
            raise ValueError('Unsupported MMU operation')
        return MMUOperation(action, gate, tool, loaded, m.fingerprint, script, label, tuple(values), enabled, expected_spool_ids)

    def start(self, operation):
        fresh = self.prepare(operation.action, operation.gate, operation.tool, operation.loaded,
                             values=operation.values, enabled=operation.enabled)
        if fresh != operation:
            raise ValueError('MMU changed; select again')
        self.operation = operation
        self.started = time.monotonic()
        self._cursor, _ = self.printer.subscription.responses_since(None)
        self._dispatch_operation = operation
        self.pending = self.printer.subscription.request(
            'printer.gcode.script', {'script': operation.script}, guard=self._dispatch_guard)
        self.phase, self.message = 'running', 'Waiting: ' + operation.label

    def _dispatch_guard(self):
        try:
            op = self._dispatch_operation
            return self.prepare(op.action, op.gate, op.tool, op.loaded,
                                ignore_pending=True, values=op.values, enabled=op.enabled) == op
        except ValueError:
            return False

    def _fail(self, message):
        if self.pending is not None:
            self.pending.cancel()  # Cancels a queued request; never replays motion.
        self.pending = None
        self.phase, self.message = 'error', message

    def _confirmed(self, m, status):
        op = self.operation
        if op.action == 'resume':
            return status.get('print_stats', {}).get('state') == 'printing' and m.locked is False
        if op.action == 'unlock':
            return m.locked is False
        if op.action == 'manual':
            return (m.tool == op.tool and m.gate == op.gate and
                    m.filament == ('loaded' if op.loaded else 'unloaded'))
        if op.action == 'recover':
            return m.filament != 'unknown'
        if m.locked is not False:
            return False
        if op.action == 'enable': return m.enabled == op.enabled
        if op.action == 'unit_select': return m.units == op.values[1] and m.unit == op.values[0] and m.gate == op.gate and m.filament == 'unloaded'
        if op.action.startswith('led_'): return m.unit == op.values[1] and m.units == op.values[2] and m.leds == op.values[3]
        if op.action == 'motors_off': return tuple(name for name, _ in m.motors) == op.values and all(v is False for _, v in m.motors) and m.sync_drive is False and m.filament == 'unloaded'
        if op.action == 'map': return m.ttg_map == op.values
        if op.action == 'endless': return m.endless_enabled == op.enabled and m.endless_groups == op.values
        if op.action == 'spool':
            return m.spool_ids == op.expected_spool_ids
        if op.action == 'check_all': return m.filament == 'unloaded' and all(v in (0, 1, 2) for v in m.gate_status)
        if op.action == 'home_selector': return m.units == op.values[0] and m.homed is True and m.tool == op.tool and m.gate == m.ttg_map[op.tool] and m.filament == 'unloaded'
        if op.action in ('grip', 'release'): return m.units == op.values[1] and m.gate == op.gate and m.unit == op.values[0] and m.grip == (op.action == 'grip') and m.filament == 'unloaded'
        if op.action in ('sync_on', 'sync_off'): return m.units == op.values[1] and m.gate == op.gate and m.unit == op.values[0] and m.sync_drive == (op.action == 'sync_on') and m.filament == 'loaded'
        if op.action == 'select': return m.gate == op.gate and m.filament == 'unloaded'
        if op.action == 'bypass': return m.gate == -2 and m.filament == 'unloaded'
        if op.action in ('load', 'change'): return m.gate == op.gate and m.filament == 'loaded' and (op.action != 'change' or m.tool == op.tool)
        if op.action in ('unload', 'unload_extruder'): return m.filament == 'unloaded'
        if op.action == 'load_extruder': return m.gate == -2 and m.filament == 'loaded'
        if op.action == 'eject': return m.gate_status[op.gate] == 0
        if op.action in ('preload', 'check'): return m.gate_status[op.gate] in (0, 1, 2) and m.filament == 'unloaded'
        return False

    def _query_objects(self):
        objects = {'mmu': None, 'print_stats': None}
        if self.operation.action == 'motors_off':
            objects['stepper_enable'] = None
        if self.operation.action.startswith('led_'):
            objects[self.operation.values[3].object_name] = None
        if self.operation.action == 'unit_select' or self.operation.action.startswith('led_'):
            objects['mmu_machine'] = None
        return objects

    def update(self):
        if self.pending is None:
            return
        p = self.printer
        m = self.state
        if p.connection_error or m is None or m.epoch != self.operation.fingerprint[0]:
            self._fail('Connection changed; check MMU')
            return
        if time.monotonic() - self.started > self.TIMEOUT:
            self._fail('Result unconfirmed; check MMU')
            return
        self._cursor, responses = p.subscription.responses_since(self._cursor)
        # Happy Hare deliberately logs automatic heating on its error channel,
        # but continues the operation. Only this known advisory is nonfatal.
        error = next((line for line in responses if line.startswith('!!')
                      and not line[2:].strip().startswith(
                          'Alert: Automatically heating extruder to ')), None)
        if error:
            self._fail(error[2:].strip() or 'MMU command failed')
            return
        if not self.pending.done():
            return
        try:
            result = self.pending.result()
            if self.phase == 'running':
                self.pending = p.subscription.request('printer.objects.query',
                    {'objects': self._query_objects()})
                self.phase, self.message = 'confirming', 'Checking MMU result'
                return
            status = result['status']
            if not isinstance(status, Mapping) or not self._query_objects().keys() <= status.keys():
                self._fail('Incomplete MMU result; check status')
                return
            snap = p.subscription.snapshot()
            snap = dict(snap, status=dict(snap['status'], **status))
            m = MMUState.from_snapshot(snap)
            if (m is None or m.epoch != self.operation.fingerprint[0]
                    or m.num_gates != self.operation.fingerprint[1]
                    or (m.enabled != self.operation.enabled if self.operation.action == 'enable' else m.enabled is not True)
                    or m.busy or not self._confirmed(m, status)):
                self._fail(m.reason if m and m.reason else 'State unconfirmed; check MMU')
                return
        except Exception:
            self._fail('Command failed; check MMU/log')
            return
        self.pending = None
        self.phase, self.message = 'complete', 'Completed: ' + self.operation.label
