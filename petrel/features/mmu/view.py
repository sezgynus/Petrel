"""MMU menu and Happy Hare home-screen rendering mixin."""

from petrel.features.mmu.overview import MMUOverviewMixin
from petrel.features.mmu.editing import MMUEditingMixin

from functools import partial as bind_arguments

from petrel.features.mmu.state import MMUState
from petrel.ui.theme import show_icon as show_theme_icon
from petrel.artwork.resources import ICON_LIBRARY_ID

class MMUViewMixin(MMUOverviewMixin, MMUEditingMixin):


    # Dedicated MMU pages own the complete 272x480 canvas. The home dashboard
    # is intentionally independent and keeps its existing appearance.
    MMU_TITLES = {'home': 'MMU', 'gates': 'GATES', 'gate': 'GATE',
                  'filament': 'FILAMENT', 'map': 'TOOL MAP', 'manage': 'MANAGE',
                  'status': 'MMU STATUS', 'bypass': 'BYPASS', 'recover': 'RECOVER STATE',
                  'manual': 'SET MMU STATE', 'confirm': 'CONFIRM',
                  'endless': 'ENDLESS SPOOL', 'group': 'GROUP MEMBERS', 'spool': 'ASSIGN SPOOL',
                  'maintenance': 'MAINTENANCE', 'options': 'MMU OPTIONS', 'more': 'MMU',
                  'leds': 'MMU LEDS', 'units': 'MMU UNITS', 'unit': 'UNIT GATES'}

    def Enter_MMU_Menu(self, page='home'):
        self._mmu_return_print = getattr(self, 'checkkey', None) in (self.PrintProcess, self.PrintErrorDetails)
        self._mmu_job_identity = self.pd.print_job_identity() if self._mmu_return_print else None
        self.checkkey = self.MMUMenu
        self._mmu_page = page
        self._mmu_selection = 0
        self._mmu_gate = 0
        self._mmu_history = []
        self._mmu_notice = ''
        self._mmu_edit = None
        self._mmu_map_draft = None
        self._mmu_endless_draft = None
        self._mmu_spool_draft = None
        self._mmu_unit_view = 0
        self._mmu_canvas_page = None
        self.Draw_MMU_Menu()

    def _mmu_open(self, page):
        self._mmu_edit = None
        if page == 'map':
            self._mmu_begin_map()
        if page == 'endless':
            self._mmu_begin_endless()
        if page == 'spool':
            self._mmu_begin_spool()
        self._mmu_history.append((self._mmu_page, self._mmu_selection))
        self._mmu_page, self._mmu_selection = page, 0
        self._mmu_notice = ''
        self.Draw_MMU_Menu()

    def _mmu_back(self):
        self._mmu_edit = None
        if self._mmu_page == 'map':
            self._mmu_map_draft = None
        if self._mmu_page == 'endless':
            self._mmu_endless_draft = None
        if self._mmu_page == 'spool':
            self._mmu_spool_draft = None
        if self._mmu_history:
            self._mmu_page, self._mmu_selection = self._mmu_history.pop()
            self._mmu_notice = ''
            self.Draw_MMU_Menu()
        elif self.pd.mmu_session.pending is not None:
            self._mmu_page, self._mmu_selection = 'home', 0
            self._mmu_notice = ''
            self.Draw_MMU_Menu()
        else:
            self._mmu_canvas_page = None
            if (getattr(self, '_mmu_return_print', False)
                    or self.pd.status in ('printing', 'paused', 'pausing')):
                self._mmu_return_print = False
                self.Goto_PrintProcess()
            else:
                self.Goto_MainMenu()
            self.Draw_Status_Area(False)
        self.lcd.update()

    def _mmu_text(self, key, value, x, y, cells=31, small=False, color=0xFFFF, bg=0x2125):
        value = str(value).replace('\n', ' ').replace('\r', ' ')
        value = value[:cells] if len(value) <= cells else value[:max(0, cells - 1)] + '~'
        width, height = (6, 12) if small else (8, 16)
        cells = min(cells, (272 - x) // width)
        value = value[:cells]
        signature = (value, x, y, cells, small, color, bg)
        if self._mmu_render.get(key) == signature:
            return
        self._mmu_render[key] = signature
        self.lcd.draw_rectangle(1, bg, x, y, min(271, x + cells * width - 1), y + height - 1)
        self.lcd.draw_text(False, False, self.lcd.font6x12 if small else self.lcd.font8x16,
                             color, bg, x, y, value)

    def _mmu_row(self, key, label, value, x, y, width, selected, enabled=True):
        label = str(label).replace('\n', ' ').replace('\r', ' ')
        value = str(value).replace('\n', ' ').replace('\r', ' ')
        signature = (label, value, selected, enabled, x, y, width)
        if self._mmu_render.get(key) == signature:
            return
        self._mmu_render[key] = signature
        bg = 0x19E9 if selected else 0x2967
        fg = 0xFFFF if enabled else 0x8410
        self.lcd.draw_rectangle(1, bg, x, y, x + width - 1, y + 39)
        if selected:
            self.lcd.draw_rectangle(0, 0xFFFF, x, y, x + width - 1, y + 39)
        cells = (width - 16) // 8
        value = str(value)[:max(0, cells - 3)]
        available = cells - (len(value) + 1 if value else 0)
        label = label[:available] if len(label) <= available else label[:max(0, available - 1)] + '~'
        self.lcd.draw_text(False, False, self.lcd.font8x16, fg, bg, x + 8, y + 12, label)
        if value:
            self.lcd.draw_text(False, False, self.lcd.font8x16, fg, bg,
                                 x + width - 8 - 8 * len(value), y + 12, value)

    @staticmethod
    def _mmu_gate_label(gate):
        return 'Bypass' if gate == -2 else 'G%d' % gate if gate is not None and gate >= 0 else 'G?'

    @staticmethod
    def _mmu_tool_label(tool):
        return 'Bypass' if tool == -2 else 'T%d' % tool if tool is not None and tool >= 0 else 'T?'


    def _mmu_items(self, m, snapshot=None):
        # Scope reuse to this item build only; never cache across UI updates.
        # Dispatch/confirmation paths continue to call prepare() with fresh data.
        if snapshot is None:
            snapshot = self.pd.subscription.snapshot()
            m = MMUState.from_snapshot(snapshot)
        prepare = bind_arguments(self.pd.mmu_session.prepare, snapshot=snapshot, parsed_state=m)
        action_item = bind_arguments(self._mmu_action_item, prepare=prepare)
        page = self._mmu_page
        nav = lambda key, label: (('page', key), label, '>', True)
        if page == 'confirm':
            return [(('cancel',), 'Cancel', '', True),
                    (('execute',), 'Confirm', '', self._mmu_confirmation_valid(prepare=prepare))]
        if page == 'home':
            tools = []
            if m:
                for tool, gate in enumerate(m.ttg_map):
                    try:
                        prepare('change', gate=gate, tool=tool)
                        enabled = not (m.tool == tool and m.filament == 'loaded')
                    except ValueError:
                        enabled = False
                    tools.append((('tool', tool, gate), 'T%d' % tool, '', enabled))
            current = m.gate if m else None
            partial = m and m.filament_pos is not None and 1 <= m.filament_pos <= 9
            primary = ('unload', 'Unload') if m and (m.filament == 'loaded' or partial) else ('load', 'Load')
            if m and m.gate == -2:
                primary = (primary[0] + '_extruder', primary[1])
            control = (nav('status', 'Recover') if self.pd.mmu_session.phase == 'error' else
                       nav('recover', 'Recover') if m and m.locked is True else
                       action_item(*primary, gate=current))
            return tools + [control, nav('more', 'More')]
        if page == 'more':
            current = m.gate if m and m.gate is not None and m.gate >= 0 else None
            primary = ('unload', 'Unload') if m and m.filament == 'loaded' else ('load', 'Load')
            return [nav('gates', 'Gates'), action_item(*primary, gate=current),
                    nav('map', 'Tool map'), nav('bypass', 'Bypass'),
                    nav('manage', 'Manage'), nav('status', 'Status')]
        if page == 'gates':
            if not m:
                return []
            return [(('gate', gate), '%s %s' % (self._mmu_gate_label(gate), m.materials[gate] or '--'),
                     self._mmu_percent(gate), True) for gate in range(m.num_gates)]
        if page == 'gate':
            gate = self._mmu_gate
            return [action_item(action, label, gate) for action, label in
                    [('select', 'Select only'), ('load', 'Load selected'), ('change', 'Load / change'),
                     ('unload', 'Unload'), ('eject', 'Eject spool'), ('preload', 'Preload'), ('check', 'Check')]] + [nav('filament', 'Filament details')]
        if page == 'bypass':
            current = m.gate if m and m.gate is not None and m.gate >= 0 else None
            return [action_item('unload', 'Unload current gate', current),
                    action_item('bypass', 'Select bypass'),
                    action_item('load_extruder', 'Load extruder'),
                    action_item('unload_extruder', 'Unload extruder')]
        if page == 'manage':
            return [nav('recover', 'Recover state'), nav('status', 'Sensors / status'),
                    nav('bypass', 'Extruder / bypass'), (('web',), 'Calibration', 'WEB', False),
                    nav('maintenance', 'Maintenance'), nav('options', 'Options')]
        if page == 'maintenance':
            items = [action_item('check_all', 'Check all gates')]
            unit = m.active_unit if m else None
            session = self.pd.mmu_session
            if unit and len(m.units) == 1 and unit.selector_type in session.HOME_SELECTORS:
                items.insert(0, action_item('home_selector', 'Home selector'))
            if unit and unit.selector_type in session.GRIP_SELECTORS:
                items += [action_item('grip', 'Grip')]
                if unit.always_gripped is False:
                    items += [action_item('release', 'Release')]
            return items + [nav('bypass', 'Extruder / bypass')]
        if page == 'options':
            unit = m.active_unit if m else None
            desired = not m.enabled if m and m.enabled is not None else None
            label = 'MMU enable / disable' if desired is None else 'Enable MMU' if desired else 'Disable MMU'
            items = [action_item('enable', label, desired_enabled=desired)]
            if unit and unit.always_gripped is not None:
                items.append(action_item('sync_on', 'Gear sync ON'))
                if not unit.always_gripped:
                    items.append(action_item('sync_off', 'Gear sync OFF'))
            if m and m.motors and all(v is not None for _, v in m.motors):
                items.append(action_item('motors_off', 'Release MMU motors'))
            if m and m.leds is not None:
                items.append(nav('leds', 'LEDs'))
            if m and len(m.units) > 1:
                items.append(nav('units', 'Units'))
            return items + [nav('status', 'Sensors / status')]
        if page == 'units':
            return [(('unit', i), 'U%d %s' % (i + 1, unit.name),
                     'G%d-G%d%s' % (unit.first_gate, unit.first_gate + unit.num_gates - 1,
                                     ' ACTIVE' if m.unit == i else ''), True)
                    for i, unit in enumerate(m.units if m else ())]
        if page == 'unit':
            index = getattr(self, '_mmu_unit_view', 0)
            if not m or not 0 <= index < len(m.units):
                return []
            unit = m.units[index]
            try:
                prepare('unit_select', values=(index,))
                enabled = True
            except ValueError:
                enabled = False
            return [(('unit_select', index, unit.first_gate), 'Select this unit', '>' if enabled else 'LOCK', enabled)] + [
                (('gate', gate), '%s %s' % (self._mmu_gate_label(gate), m.materials[gate] or '--'),
                 self._mmu_percent(gate), True) for gate in range(unit.first_gate, unit.first_gate + unit.num_gates)]
        if page == 'leds':
            if not m or not m.leds:
                return []
            leds = m.leds
            items = [action_item('led_enable', 'LEDs OFF' if leds.enabled else 'LEDs ON', desired_enabled=not leds.enabled if leds.enabled is not None else None),
                     action_item('led_animation', 'Animation OFF' if leds.animation else 'Animation ON', desired_enabled=not leds.animation if leds.animation is not None else None)]
            if leds.segments[0]:
                for mode in self.pd.mmu_session.LED_MODES:
                    try:
                        prepare('led_mode', values=(mode,))
                        enabled = True
                    except ValueError:
                        enabled = False
                    items.append((('led_mode', mode), mode.replace('_', ' ').title(), '>' if enabled else 'LOCK', enabled))
            return items
        if page == 'filament':
            return [nav('spool', 'Assign spool ID')]
        if page == 'spool':
            writable = self._mmu_spool_writable(m, prepare=prepare)
            return [(('spool_edit',), 'Spool ID', '#%d' % self._mmu_spool_draft, writable),
                    (('spool_save',), 'Save', '>' if writable else 'LOCK',
                     writable and self._mmu_spool_draft != self._mmu_spool_original),
                    (('spool_clear',), 'Clear assignment', '>', writable and self._mmu_spool_original is not None and self._mmu_spool_original > 0),
                    (('cancel',), 'Cancel', '', True)]
        if page == 'recover':
            return [action_item('recover', 'Auto recover'), nav('manual', 'Set state manually'),
                    action_item('unlock', 'Unlock / reheat'),
                    action_item('resume', 'Resume print')]
        if page == 'map':
            draft = self._mmu_map_draft
            writable = self._mmu_map_writable(m, prepare=prepare)
            return [(('map_edit', tool), 'T%d' % tool, self._mmu_gate_label(gate), writable)
                    for tool, gate in enumerate(draft)] + [
                        nav('endless', 'EndlessSpool'),
                        (('map_save',), 'Save', '>' if writable else 'LOCK',
                         writable and tuple(draft) != self._mmu_map_original),
                        (('cancel',), 'Cancel', '', True)]
        if page in ('endless', 'group'):
            draft = self._mmu_endless_draft
            writable = self._mmu_endless_writable(m, prepare=prepare)
            groups = draft['groups']
            if page == 'group':
                return [(('member', gate), '%s %s %s' % (self._mmu_gate_label(gate),
                         (m.materials[gate] or '--') if m and gate < m.num_gates else '--',
                         (m.colors[gate] or '--') if m and gate < m.num_gates else '--'),
                         'IN' if group == self._mmu_group else 'OUT', writable)
                        for gate, group in enumerate(groups)]
            ids = sorted({g for g in groups if g is not None})
            changed = (draft['enabled'], tuple(groups)) != self._mmu_endless_original
            return [(('endless_toggle',), 'Enabled', {True: 'ON', False: 'OFF', None: '--'}[draft['enabled']], writable)] + [
                (('group', group), 'Group %d' % (i + 1), self._mmu_group_summary(group), True)
                for i, group in enumerate(ids)] + [
                (('endless_save',), 'Save', '>' if writable else 'LOCK', writable and changed),
                (('cancel',), 'Cancel', '', True)]
        if page == 'manual':
            draft = self._mmu_manual
            return [(('edit', 'tool'), 'Tool', self._mmu_tool_label(draft['tool']), True),
                    (('edit', 'gate'), 'Gate', self._mmu_gate_label(draft['gate']), True),
                    (('edit', 'loaded'), 'Filament', 'LOADED' if draft['loaded'] else 'UNLOADED', True),
                    (('apply',), 'Apply', '>', m is not None), (('cancel',), 'Cancel', '', True)]
        if page == 'status':
            if self.pd.mmu_session.phase == 'error':
                return [(('ack',), 'Acknowledge', '', True), nav('recover', 'Recover state')]
            return []
        return []


    def Draw_MMU_Menu(self):
        self._sync_fan_animation(False)
        if not hasattr(self, '_mmu_page'):
            self._mmu_page, self._mmu_selection = 'home', 0
            self._mmu_gate, self._mmu_history, self._mmu_notice = 0, [], ''
        page = self._mmu_page
        snapshot = self.pd.subscription.snapshot()
        m = MMUState.from_snapshot(snapshot)
        prepare = bind_arguments(self.pd.mmu_session.prepare, snapshot=snapshot, parsed_state=m)
        if (getattr(self, '_mmu_canvas_page', None) != page or
                page == 'home' and getattr(self, '_mmu_available', None) != (m is not None)):
            self._list_render = None
            self._mmu_list_window = None
            self._mmu_spool_page = None
            self._mmu_filament_view = None
            self.lcd.draw_rectangle(1, 0x2125, 0, 0, 271, 479)
            self.lcd.draw_rectangle(1, 0x2966, 0, 0, 271, 29)
            self._mmu_canvas_page, self._mmu_render = page, {}
            self._mmu_available = m is not None
            self._invalidate_header()
        if page == 'map' and getattr(self, '_mmu_map_draft', None) is None:
            self._mmu_begin_map()
        if page in ('endless', 'group') and getattr(self, '_mmu_endless_draft', None) is None:
            self._mmu_begin_endless()
        if page == 'spool' and getattr(self, '_mmu_spool_draft', None) is None:
            self._mmu_begin_spool()
        if page == 'manual' and not hasattr(self, '_mmu_manual'):
            self._mmu_manual_base = m.fingerprint if m else None
            self._mmu_manual = {'tool': m.tool if m and m.tool is not None and m.tool >= 0 else 0,
                                'gate': m.gate if m and m.gate is not None and m.gate >= 0 else 0,
                                'loaded': bool(m and m.filament == 'loaded')}
        items = self._mmu_items(m, snapshot=snapshot)
        self._mmu_drawn_keys = tuple(item[0] for item in items)
        self._mmu_selection = min(self._mmu_selection, len(items))
        back_selected = self._mmu_selection == 0
        if self._mmu_render.get('back') != back_selected:
            self._mmu_render['back'] = back_selected
            self.lcd.draw_rectangle(1, 0x19E9 if back_selected else 0x2966,
                                    4, 3, 27, 26)
            show_theme_icon(self.lcd, ICON_LIBRARY_ID, self.ICON_Back, 6, 5)
        title = self.MMU_TITLES[page]
        if page in ('gate', 'filament', 'spool'):
            title += ' / ' + self._mmu_gate_label(self._mmu_gate)
        self._mmu_text('title', title, 34, 6, 19, bg=0x2966)
        self._draw_header_clock()
        connection = 'OFFLINE' if self.pd.connection_error else 'MMU unavailable' if not m else (
            'MMU DISABLED' if m.enabled is not True else m.action.upper())
        if page != 'home':
            self._mmu_text('connection', connection, 10, 36, 42, small=True,
                           color=0xFD20 if not m or m.enabled is not True else 0x8410)
        first_y, visible = 67, 8
        if page == 'home':
            self._mmu_draw_overview(m, items)
            first_y = None
        elif page == 'gate':
            gate = self._mmu_gate
            if m and gate < m.num_gates:
                tools = ','.join('T%d' % t for t in m.tools_for_gate(gate)) or 'Unmapped'
                self._mmu_text('summary', tools + ' / ' + (m.materials[gate] or '--'), 12, 68)
                state = m.filament.upper() if gate == m.gate else {-1: 'UNKNOWN', 0: 'EMPTY', 1: 'AVAILABLE', 2: 'BUFFERED'}.get(m.gate_status[gate], 'UNKNOWN')
                self._mmu_text('gatestate', state + ' / ' + self._mmu_percent(gate), 12, 98)
            first_y, visible = 132, 7
        elif page == 'filament':
            gate = self._mmu_gate
            if m and gate < m.num_gates:
                for i, (label, value) in enumerate((('Name', m.names[gate]), ('Material', m.materials[gate]),
                        ('Color', m.colors[gate]),
                        ('Spool ID', '#%s' % m.spool_ids[gate] if m.spool_ids[gate] and m.spool_ids[gate] > 0 else '--'),
                        ('Remaining', self._mmu_percent(gate)), ('Temperature', '%s C' % m.temperatures[gate] if m.temperatures[gate] is not None else '--'),
                        ('Spoolman', m.spoolman_support))):
                    self._mmu_text('meta%d' % i, label + ': ' + str(value or '--'), 12, 70 + 37 * i)
                self._mmu_text('readonly', 'Metadata: read-only; use web UI', 12, 338, 40, small=True)
            first_y, visible = 376, 1
        elif page == 'spool':
            writable = self._mmu_spool_writable(m, prepare=prepare)
            old = self._mmu_spool_original
            self._mmu_text('oldspool', 'Current: ' + ('#%d' % old if old and old > 0 else '--'), 12, 66)
            self._mmu_text('spoolmode', 'Spoolman: ' + (m.spoolman_support if m else 'Unknown'), 12, 99, 40, small=True)
            self._mmu_text('spoolhint', 'Press ID, turn number, press again', 12, 124, 40, small=True)
            self._mmu_text('spooldraft', 'Changes wait for Save' if writable else 'Locked; check mode/state/metadata', 12, 148, 40, small=True, color=0x8410 if writable else 0xFD20)
            first_y, visible = 180, 6
        elif page in ('maintenance', 'options'):
            unit = m.active_unit if m else None
            self._mmu_text('unitname', unit.name if unit else 'Hardware data unavailable', 12, 66)
            self._mmu_text('unittype', unit.selector_type if unit else 'Unsupported controls hidden', 12, 94, 40, small=True)
            self._mmu_text('maintstate', 'Filament: ' + (m.filament.upper() if m else 'UNKNOWN'), 12, 123)
            detail = ('Grip: ' + {True: 'GRIPPED', False: 'RELEASED', None: '--'}[m.grip]
                      if page == 'maintenance' and m else 'Gear sync: ' + {True: 'ON', False: 'OFF', None: '--'}[m.sync_drive]
                      if m else 'Live state unavailable')
            self._mmu_text('maintdetail', detail, 12, 152)
            first_y, visible = 191, 5
        elif page in ('unit', 'units'):
            index = getattr(self, '_mmu_unit_view', 0)
            unit = m.units[index] if m and 0 <= index < len(m.units) else None
            self._mmu_text('unitview', unit.name if page == 'unit' and unit else 'Browse units; no movement', 12, 66)
            self._mmu_text('unithelp', 'Select moves to the first gate' if page == 'unit' else 'Gate numbers remain global', 12, 98, 40, small=True)
            first_y, visible = 134, 7
        elif page == 'leds':
            unit = m.active_unit if m else None
            self._mmu_text('ledunit', unit.name if unit else 'LED state unavailable', 12, 66)
            mode = m.leds.exit_effect if m and m.leds else '--'
            self._mmu_text('ledmode', 'Exit: ' + mode, 12, 98, 40, small=True)
            self._mmu_text('ledscope', 'Only the active unit is changed', 12, 119, 40, small=True)
            first_y, visible = 148, 6
        elif page == 'map':
            writable = self._mmu_map_writable(m, prepare=prepare)
            self._mmu_text('maphint', 'Press row, turn gate, press again', 12, 66, 40, small=True)
            self._mmu_text('mapdraft', 'Changes wait for Save' if writable else 'Locked; reopen after state change',
                           12, 87, 40, small=True, color=0x8410 if writable else 0xFD20)
            first_y, visible = 114, 7
        elif page in ('endless', 'group'):
            writable = self._mmu_endless_writable(m, prepare=prepare)
            hint = 'Changes wait for Save' if writable else 'Locked; reopen after state change'
            if page == 'group':
                members = [i for i, g in enumerate(self._mmu_endless_draft['groups'])
                           if g == self._mmu_group and m and i < m.num_gates]
                materials = {(m.materials[i] or '--').strip().lower() for i in members} if m else set()
                colors = {(m.colors[i] or '--').strip().lower() for i in members} if m else set()
                known = members and '--' not in materials and '--' not in colors
                compatibility = ('Mixed material / color' if len(materials) > 1 or len(colors) > 1
                                 else 'Same material / color' if known else 'Compatibility unknown')
                self._mmu_text('groupcompat', compatibility, 12, 66, 40, small=True, color=0xFD20)
                self._mmu_text('grouphelp', 'Press gate: join / split group', 12, 87, 40, small=True)
                self._mmu_text('grouplock', hint, 12, 108, 40, small=True)
                first_y, visible = 134, 7
            else:
                self._mmu_text('endlesshint', hint, 12, 66, 40, small=True, color=0x8410 if writable else 0xFD20)
                self._mmu_text('endlesshelp', 'Open group to choose member gates', 12, 87, 40, small=True)
                first_y, visible = 114, 7
        elif page == 'status':
            session = self.pd.mmu_session
            self._mmu_text('result', session.message or 'Live MMU telemetry', 12, 66, 40, small=True, color=0xFD20 if session.phase == 'error' else 0xFFFF)
            if m:
                self._mmu_text('active', '%s / %s / %s' % (self._mmu_tool_label(m.tool), self._mmu_gate_label(m.gate), m.filament.upper()), 12, 100)
                self._mmu_path(m, 132)
                progress = 'Bowden: %d%%' % m.bowden_progress if m.bowden_progress is not None else 'Stage: ' + m.action
                self._mmu_text('progress', progress, 12, 186)
                sensors = dict(m.sensors)
                for i, sensor in enumerate(('mmu_shared_exit', 'extruder', 'toolhead')):
                    value = 'ABSENT' if sensor not in sensors else {True: 'TRIGGERED', False: 'CLEAR', None: 'UNKNOWN/OFF'}[sensors[sensor]]
                    self._mmu_text('sensor%d' % i, sensor + ': ' + value, 12, 218 + i * 27, 40, small=True)
                self._mmu_text('sync', 'Gear sync: ' + {True: 'ON', False: 'OFF', None: '--'}[m.sync_drive], 12, 306)
                self._mmu_nozzle(336)
            first_y, visible = 376, 2
        elif page == 'bypass':
            self._mmu_text('filament', 'Filament: ' + (m.filament.upper() if m else 'UNKNOWN'), 12, 75)
            self._mmu_text('hint', 'Unload before selecting bypass', 12, 105, 40, small=True)
            first_y, visible = 156, 6
        elif page == 'recover':
            if m:
                reason = m.reason or ('MMU locked' if m.locked else 'Check physical filament state')
                for i in range(3):
                    self._mmu_text('reason%d' % i, reason[i * 40:(i + 1) * 40], 12, 66 + i * 17, 40, small=True, color=0xFD20)
                self._mmu_text('active', '%s / %s / %s' % (self._mmu_tool_label(m.tool), self._mmu_gate_label(m.gate), m.filament.upper()), 12, 131)
            first_y, visible = 186, 6
        elif page == 'manual':
            self._mmu_text('hint', 'Report actual state; no movement', 12, 70, 40, small=True)
            first_y, visible = 113, 7
        elif page == 'confirm':
            op = self._mmu_confirmation
            self._mmu_text('target', op.label, 12, 82)
            summary = 'Physical state: ' + (m.filament.upper() if m else 'UNKNOWN')
            self._mmu_text('details', summary, 12, 120, 40, small=True)
            self._mmu_text('valid', 'Target changed; cancel and retry' if not self._mmu_confirmation_valid(prepare=prepare) else 'Check target before confirming', 12, 170, 40, small=True, color=0xFD20)
            message = {'unload': 'Filament returns to MMU.', 'eject': 'Spool removed from MMU.',
                       'manual': 'Reports state; does not move.', 'map': 'Saves mapping; no filament movement.',
                       'endless': 'Saves groups; no filament movement.', 'resume': 'Print motion will resume.'}.get(op.action, 'This may move filament/motors.')
            if op.action == 'spool':
                message = 'Saves spool ID; no filament movement.'
            if op.action in ('grip', 'release'):
                message = 'Moves grip/selector at current gate.'
            if op.action in ('sync_on', 'sync_off'):
                message = 'Changes gear drive and grip state.'
            if op.action == 'home_selector':
                message = 'Homes selector, then selects tool.'
            if op.action == 'check_all':
                message = 'Moves filament across all gates.'
            if op.action == 'enable':
                message = 'Resets MMU state.' if op.enabled else 'Disables MMU and releases motors.'
            if op.action == 'motors_off':
                message = 'All MMU units; home may be lost.'
            if op.action.startswith('led_'):
                message = 'Changes LEDs on the target unit.'
            if op.action == 'unit_select':
                message = 'May home / move the selector'
            self._mmu_text('effect', message, 12, 210, 40, small=True)
            if op.action.startswith('led_') or op.action == 'unit_select':
                index = op.values[1] if op.action.startswith('led_') else op.values[0]
                unit = m.units[index] if m and 0 <= index < len(m.units) else None
                self._mmu_text('targetunit', unit.name if unit else 'Target unit unavailable', 12, 241, 40, small=True)
            if op.action == 'map':
                old = m.ttg_map if m else ()
                changes = [(tool, gate) for tool, gate in enumerate(op.values)
                           if tool >= len(old) or old[tool] != gate]
                for row in range(5):
                    value = ('T%d > %s' % (changes[row][0], self._mmu_gate_label(changes[row][1]))
                             if row < min(4, len(changes)) else
                             '+%d more changes' % (len(changes) - 4) if row == 4 and len(changes) > 4 else '')
                    self._mmu_text('change%d' % row, value, 12, 241 + row * 20, 40, small=True)
            if op.action == 'endless':
                self._mmu_text('enablechange', 'Enabled: ' + ('ON' if op.enabled else 'OFF'), 12, 241)
                changes = [(gate, group) for gate, group in enumerate(op.values)
                           if m and (gate >= m.num_gates or m.endless_groups[gate] != group)]
                ids = sorted(set(op.values))
                for row in range(4):
                    value = ('%s > Group %d' % (self._mmu_gate_label(changes[row][0]), ids.index(changes[row][1]) + 1)
                             if row < min(3, len(changes)) else
                             '+%d more changes' % (len(changes) - 3) if row == 3 and len(changes) > 3 else '')
                    self._mmu_text('groupchange%d' % row, value, 12, 269 + row * 20, 40, small=True)
            if op.action == 'spool':
                old = m.spool_ids[op.gate] if m and op.gate < m.num_gates else None
                self._mmu_text('spoolchange', '%s: %s > %s' % (self._mmu_gate_label(op.gate),
                               '#%d' % old if old and old > 0 else '--',
                               '#%d' % op.values[0] if op.values[0] > 0 else '--'), 12, 241, 40, small=True)
                moved = [self._mmu_gate_label(gate) for gate, sid in enumerate(m.spool_ids if m else ())
                         if gate != op.gate and sid == op.values[0] and sid > 0]
                warning = 'Moves ID off: ' + ', '.join(moved) if moved else 'Other assignments preserved'
                self._mmu_text('spoolmove', warning, 12, 271, 40, small=True, color=0xFD20)
            for i, (_, label, _, enabled) in enumerate(items):
                self._mmu_row('item%d' % i, label, '', 8 + i * 132, 374, 124,
                              self._mmu_selection == i + 1, enabled)
            first_y = None
        if first_y is not None:
            window = getattr(self, '_mmu_list_window', None)
            keys = tuple(item[0] for item in items)
            same = window is not None and window[:3] == (page, first_y, visible) and window[4] == keys
            start = window[3] if same else 0
            start = max(0, min(start, max(0, self._mmu_selection - 1)), self._mmu_selection - visible)
            delta = start - window[3] if same else 0
            if delta and abs(delta) < visible:
                # Remove the old highlight before moving the LCD pixels.
                for row in range(visible):
                    sig = self._mmu_render.get('row%d' % row)
                    if sig and sig[2]:
                        self._mmu_row('row%d' % row, sig[0], sig[1], sig[4], sig[5], sig[6], False, sig[3])
                self.lcd.move_area(1,
                    self.DWIN_SCROLL_UP if delta > 0 else self.DWIN_SCROLL_DOWN,
                    abs(delta) * 43, 0x2125, 8, first_y, 263, first_y + visible * 43 - 1)
                shifted = {}
                for row in range(visible):
                    sig = self._mmu_render.pop('row%d' % row, None)
                    target = row - delta
                    if sig is not None and 0 <= target < visible:
                        sig = list(sig)
                        sig[5] -= delta * 43
                        shifted['row%d' % target] = tuple(sig)
                self._mmu_render.update(shifted)
            self._mmu_list_window = (page, first_y, visible, start, keys)
            for row in range(visible):
                i = start + row
                if i < len(items):
                    _, label, value, enabled = items[i]
                    if page == 'map' and items[i][0][0] == 'map_edit' and getattr(self, '_mmu_edit', None) == ('map', items[i][0][1]):
                        value = '[' + value + ']'
                    if page == 'endless' and items[i][0][0] == 'endless_toggle' and getattr(self, '_mmu_edit', None) == ('endless', 'enabled'):
                        value = '[' + value + ']'
                    if page == 'spool' and items[i][0][0] == 'spool_edit' and getattr(self, '_mmu_edit', None) == ('spool', 'id'):
                        value = '[' + value + ']'
                    if page == 'manual' and items[i][0][0] == 'edit' and getattr(self, '_mmu_edit', None) == items[i][0][1]:
                        value = '[' + value + ']'
                    self._mmu_row('row%d' % row, label, value, 8, first_y + row * 43, 256,
                                  self._mmu_selection == i + 1, enabled)
                elif self._mmu_render.get('row%d' % row) is not None:
                    self.lcd.draw_rectangle(1, 0x2125, 8, first_y + row * 43, 263, first_y + row * 43 + 39)
                    self._mmu_render.pop('row%d' % row, None)
            if len(items) > visible:
                self._mmu_text('pagination', '%d-%d / %d' % (start + 1, min(len(items), start + visible), len(items)), 12, 436, 40, small=True)
        if page != 'home':
            self._mmu_text('footer', self._mmu_notice, 10, 463, 42, small=True, color=0xFD20)
        self.lcd.update()


    def _mmu_power_popup_stale(self):
        return (getattr(self, 'checkkey', None) == self.PowerConfirm and getattr(self, '_power_origin', None) == self.MMUMenu
                and (self.pd.connection_error or not self.pd.state.ready
                     or getattr(self, '_power_origin_epoch', None) != self.pd.state.epoch))

    def _poll_mmu(self):
        session = self.pd.mmu_session
        was_pending = session.pending is not None
        session.update()
        if self._mmu_power_popup_stale():
            self._restore_power_origin()
        if self.checkkey == self.MMUMenu:
            if self.pd.connection_error and getattr(self, '_power_focus', False):
                self._power_focus = False
            if was_pending and getattr(self, '_mmu_page', 'home') not in ('home', 'status') and session.phase == 'error':
                self._mmu_page, self._mmu_selection = 'status', 1
            self.Draw_MMU_Menu()
