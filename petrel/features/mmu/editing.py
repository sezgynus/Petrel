"""MMU edit drafts, confirmation guards and existing encoder actions."""
from petrel.features.mmu.state import MMUState


class MMUEditingMixin:
    def _mmu_action_item(self, action, label, gate=None, desired_enabled=None, prepare=None):
        key = ('action', action, gate) if desired_enabled is None else ('action', action, gate, desired_enabled)
        try:
            (prepare or self.pd.mmu_session.prepare)(action, gate=gate, enabled=desired_enabled)
        except ValueError:
            return (key, label, 'LOCK', False)
        return (key, label, '>', True)

    def _mmu_begin_map(self):
        m = self.pd.mmu_session.state
        self._mmu_map_draft = list(m.ttg_map) if m else []
        self._mmu_map_base = m.fingerprint if m else None
        self._mmu_map_original = tuple(self._mmu_map_draft)

    def _mmu_map_writable(self, m, prepare=None):
        if m is None or m.fingerprint != getattr(self, '_mmu_map_base', None):
            return False
        try:
            (prepare or self.pd.mmu_session.prepare)('map', values=self._mmu_map_draft)
        except ValueError:
            return False
        return True

    def _mmu_begin_endless(self):
        m = self.pd.mmu_session.state
        self._mmu_endless_draft = {'enabled': m.endless_enabled if m else None,
                                   'groups': list(m.endless_groups) if m else []}
        self._mmu_endless_base = m.fingerprint if m else None
        self._mmu_endless_original = (self._mmu_endless_draft['enabled'], tuple(self._mmu_endless_draft['groups']))
        self._mmu_group = next((g for g in self._mmu_endless_draft['groups'] if g is not None), 0)

    def _mmu_endless_writable(self, m, prepare=None):
        if m is None or m.fingerprint != getattr(self, '_mmu_endless_base', None):
            return False
        draft = self._mmu_endless_draft
        try:
            (prepare or self.pd.mmu_session.prepare)('endless', values=draft['groups'], enabled=draft['enabled'])
        except ValueError:
            return False
        return True

    def _mmu_group_summary(self, group):
        gates = [self._mmu_gate_label(i) for i, g in enumerate(self._mmu_endless_draft['groups']) if g == group]
        return ' '.join(gates[:3]) + (' +%d' % (len(gates) - 3) if len(gates) > 3 else '')

    def _mmu_begin_spool(self):
        m = self.pd.mmu_session.state
        sid = m.spool_ids[self._mmu_gate] if m and self._mmu_gate < m.num_gates else None
        self._mmu_spool_draft = sid if sid is not None and sid > 0 else 1
        self._mmu_spool_original = sid
        self._mmu_spool_base = m.fingerprint if m else None

    def _mmu_spool_writable(self, m, prepare=None):
        if m is None or m.fingerprint != getattr(self, '_mmu_spool_base', None):
            return False
        try:
            (prepare or self.pd.mmu_session.prepare)('spool', gate=self._mmu_gate, values=(self._mmu_spool_draft,))
        except ValueError:
            return False
        return True

    def _mmu_confirmation_valid(self, prepare=None):
        op = getattr(self, '_mmu_confirmation', None)
        if op is None:
            return False
        try:
            return (prepare or self.pd.mmu_session.prepare)(op.action, op.gate, op.tool, op.loaded,
                                               values=op.values, enabled=op.enabled) == op
        except ValueError:
            return False

    def HMI_MMU_Menu(self):
        if not hasattr(self, '_mmu_page'):
            self.Draw_MMU_Menu()
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        snapshot = self.pd.subscription.snapshot()
        m = MMUState.from_snapshot(snapshot)
        edit = getattr(self, '_mmu_edit', None)
        if edit:
            if event == self.ENCODER_DIFF_ENTER:
                self._mmu_edit = None
            elif isinstance(edit, tuple) and edit[0] == 'map':
                if not self._mmu_map_writable(m):
                    self._mmu_edit = None
                    self._mmu_notice = 'MMU changed; reopen editor'
                elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                    delta = getattr(self,"_rotation_steps",1)*(1 if event == self.ENCODER_DIFF_CW else -1)
                    tool = edit[1]
                    self._mmu_map_draft[tool] = max(0, min(m.num_gates - 1, self._mmu_map_draft[tool] + delta))
            elif edit == ('endless', 'enabled'):
                if not self._mmu_endless_writable(m):
                    self._mmu_edit = None
                    self._mmu_notice = 'MMU changed; reopen editor'
                elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                    self._mmu_endless_draft['enabled'] = event == self.ENCODER_DIFF_CW
            elif edit == ('spool', 'id'):
                if not self._mmu_spool_writable(m):
                    self._mmu_edit = None
                    self._mmu_notice = 'MMU changed; reopen editor'
                elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                    delta = getattr(self,"_rotation_steps",1)*(1 if event == self.ENCODER_DIFF_CW else -1)
                    self._mmu_spool_draft = max(1, self._mmu_spool_draft + delta)
            elif m and event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                delta = getattr(self,"_rotation_steps",1)*(1 if event == self.ENCODER_DIFF_CW else -1)
                self._mmu_manual[edit] = ((not self._mmu_manual[edit] if getattr(self,'_rotation_steps',1)%2 else self._mmu_manual[edit]) if edit == 'loaded'
                    else max(0, min(m.num_gates - 1, self._mmu_manual[edit] + delta)))
            self.Draw_MMU_Menu()
            return
        items = self._mmu_items(m, snapshot=snapshot)
        if event == self.ENCODER_DIFF_ENTER and tuple(item[0] for item in items) != self._mmu_drawn_keys:
            self._mmu_notice = 'Menu changed; select again'
            self.Draw_MMU_Menu()
            return
        self._mmu_selection = min(self._mmu_selection, len(items))
        if event == self.ENCODER_DIFF_CW:
            self._mmu_selection = min(len(items), self._mmu_selection + getattr(self,"_rotation_steps",1))
        elif event == self.ENCODER_DIFF_CCW:
            self._mmu_selection = max(0, self._mmu_selection - getattr(self,"_rotation_steps",1))
        elif event == self.ENCODER_DIFF_ENTER:
            if self._mmu_selection == 0:
                self._mmu_back()
                return
            key, _, _, enabled = items[self._mmu_selection - 1]
            if not enabled:
                if self._mmu_page == 'home' and key[0] in ('tool', 'action'):
                    try:
                        if key[0] == 'tool':
                            self.pd.mmu_session.prepare('change', gate=key[2], tool=key[1])
                        else:
                            self.pd.mmu_session.prepare(key[1], gate=key[2])
                    except ValueError as error:
                        self._mmu_notice = str(error)
                else:
                    self._mmu_notice = 'Unavailable in current state'
            elif self._mmu_page == 'home' and key[0] in ('tool', 'action'):
                try:
                    operation = (self.pd.mmu_session.prepare('change', gate=key[2], tool=key[1]) if key[0] == 'tool'
                                 else self.pd.mmu_session.prepare(key[1], gate=key[2]))
                    self.pd.mmu_session.start(operation)
                except ValueError as error:
                    self._mmu_notice = str(error)
                else:
                    self._mmu_notice = ''
            elif key[0] == 'page':
                if key[1] == 'manual':
                    self._mmu_manual_base = m.fingerprint if m else None
                    self._mmu_manual = {'tool': m.tool if m and m.tool is not None and m.tool >= 0 else 0,
                                        'gate': m.gate if m and m.gate is not None and m.gate >= 0 else 0,
                                        'loaded': bool(m and m.filament == 'loaded')}
                    self._mmu_edit = None
                self._mmu_open(key[1])
                return
            elif key[0] == 'gate':
                self._mmu_gate = key[1]
                self._mmu_open('gate')
                return
            elif key[0] == 'unit':
                self._mmu_unit_view = key[1]
                self._mmu_open('unit')
                return
            elif key[0] == 'map_edit':
                self._mmu_edit = ('map', key[1])
            elif key[0] == 'endless_toggle':
                self._mmu_edit = ('endless', 'enabled')
            elif key[0] == 'spool_edit':
                self._mmu_edit = ('spool', 'id')
            elif key[0] == 'group':
                self._mmu_group = key[1]
                self._mmu_open('group')
                return
            elif key[0] == 'member':
                groups = self._mmu_endless_draft['groups']
                gate = key[1]
                if groups[gate] != self._mmu_group:
                    groups[gate] = self._mmu_group
                elif groups.count(self._mmu_group) > 1:
                    new_group = 0
                    while new_group in groups:
                        new_group += 1
                    groups[gate] = new_group
            elif key[0] in ('action', 'apply', 'map_save', 'endless_save', 'spool_save', 'spool_clear', 'unit_select', 'led_mode'):
                try:
                    if key[0] == 'apply' and (m is None or m.fingerprint != self._mmu_manual_base):
                        raise ValueError('MMU changed; reopen editor')
                    if key[0] == 'unit_select':
                        self._mmu_confirmation = self.pd.mmu_session.prepare('unit_select', values=(key[1],))
                    elif key[0] == 'led_mode':
                        self._mmu_confirmation = self.pd.mmu_session.prepare('led_mode', values=(key[1],))
                    elif key[0] in ('spool_save', 'spool_clear'):
                        if not self._mmu_spool_writable(m):
                            raise ValueError('MMU changed; reopen editor')
                        sid = -1 if key[0] == 'spool_clear' else self._mmu_spool_draft
                        self._mmu_confirmation = self.pd.mmu_session.prepare('spool', gate=self._mmu_gate, values=(sid,))
                    elif key[0] == 'endless_save':
                        if not self._mmu_endless_writable(m):
                            raise ValueError('MMU changed; reopen editor')
                        draft = self._mmu_endless_draft
                        self._mmu_confirmation = self.pd.mmu_session.prepare('endless', values=draft['groups'], enabled=draft['enabled'])
                    elif key[0] == 'map_save':
                        if not self._mmu_map_writable(m):
                            raise ValueError('MMU changed; reopen editor')
                        self._mmu_confirmation = self.pd.mmu_session.prepare('map', values=self._mmu_map_draft)
                    else:
                        self._mmu_confirmation = (self.pd.mmu_session.prepare(key[1], gate=key[2], enabled=key[3] if len(key) > 3 else None)
                            if key[0] == 'action' else self.pd.mmu_session.prepare('manual', **self._mmu_manual))
                except ValueError as error:
                    self._mmu_notice = str(error)
                else:
                    self._mmu_open('confirm')
                    self._mmu_selection = 1  # Cancel always owns initial focus.
                    self.Draw_MMU_Menu()
                    return
            elif key[0] == 'execute':
                try:
                    self.pd.mmu_session.start(self._mmu_confirmation)
                except ValueError as error:
                    self._mmu_notice = str(error)
                else:
                    # Drop confirmation so Back can never submit it again.
                    if self._mmu_confirmation.action == 'map':
                        self._mmu_map_draft = None
                    if self._mmu_confirmation.action == 'endless':
                        self._mmu_endless_draft = None
                    if self._mmu_confirmation.action == 'spool':
                        self._mmu_spool_draft = None
                    self._mmu_page, self._mmu_selection = 'status', 0
                    self.Draw_MMU_Menu()
                    return
            elif key[0] == 'cancel':
                self._mmu_back()
                return
            elif key[0] == 'edit':
                self._mmu_edit = key[1]
            elif key[0] == 'ack':
                self.pd.mmu_session.phase, self.pd.mmu_session.message = 'idle', ''
        self.Draw_MMU_Menu()
