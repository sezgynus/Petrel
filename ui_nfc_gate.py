"""Global NFC spool-to-gate prompt, using the existing guarded MMU session."""
from lcd_resources import ICON_NFC


class NFCGateViewMixin:
    def _nfc_gate_result(self):
        router = getattr(self, '_nfc_spool_router', None)
        result = router.take_result() if router is not None else None
        if result is None:
            return
        uid, spool = result
        if uid is None:
            if getattr(self, '_nfc_gate_popup', None):
                self._nfc_gate_close()
            return
        if (not self._uart_online or self._closed or getattr(self, '_boot_active', False)
                or getattr(self, '_nfc_share_popup', None)
                or self.checkkey == self.PowerConfirm
                or getattr(self, '_power_hold_started', None) is not None):
            return
        existing = getattr(self, '_nfc_gate_popup', None)
        if existing and existing['phase'] in ('checking', 'writing'):
            return
        self._update_ui_state()
        self._display_activity()
        self._nfc_gate_popup = {
            'uid': uid, 'spool': spool,
            'origin': existing['origin'] if existing else self.checkkey,
            'epoch': self.pd.state.epoch, 'selection': 0,
            'phase': 'choose', 'message': '', 'operation': None}
        self.checkkey = self.NFCGateMenu
        self._list_render = None
        self._nfc_gate_draw()
        self.lcd.update()

    def _nfc_gate_choices(self):
        popup = self._nfc_gate_popup
        session = self.pd.mmu_session
        state = session.state
        rows = [('Cancel', self.ICON_Back, None, None)]
        operations = [None]
        reason = 'MMU unavailable'
        if state is not None:
            for gate in range(state.num_gates):
                try:
                    operation = session.prepare('spool', gate=gate,
                                                values=(popup['spool'].id,))
                except ValueError as error:
                    reason = str(error)
                    continue
                old = state.spool_ids[gate]
                label = self._mmu_gate_label(gate)
                label += '  #' + str(old) if old is not None and old > 0 else '  Empty'
                rows.append((label, ICON_NFC, None, None))
                operations.append(operation)
        return rows, operations, reason

    def _nfc_gate_draw(self):
        popup = self._nfc_gate_popup
        phase = popup['phase']
        spool = popup['spool']
        if phase == 'choose':
            rows, operations, reason = self._nfc_gate_choices()
            popup['operations'] = operations
            popup['selection'] = min(popup['selection'], len(rows) - 1)
            self._draw_list_menu('Spool #%d: choose gate' % spool.id, rows, popup['selection'])
            if len(rows) == 1:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 92, 263, 351)
                for index, line in enumerate(self._spool_lines(reason, limit=3)):
                    self._draw_menu_text(line, 8, 104 + index * 22)
                self._spool_draw_summary(spool)
            return
        self._draw_list_menu('Spool #%d gate' % spool.id,
            [('Close', self.ICON_Back, None, None)], 0)
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 92, 263, 351)
        for index, line in enumerate(self._spool_lines(popup['message'], limit=2)):
            self._draw_menu_text(line, 8, 104 + index * 22)
        self._spool_draw_summary(spool)

    def _nfc_gate_verify(self):
        popup = getattr(self, '_nfc_gate_popup', None)
        if not popup or self.checkkey != self.NFCGateMenu or popup['phase'] != 'checking':
            return
        future = popup['future']
        if not future.done():
            return
        try:
            # The tag may have been moved in Spoolman while the prompt was open.
            if future.result() != popup['spool']:
                raise ValueError('Tag binding changed; scan again')
            self.pd.mmu_session.start(popup['operation'])
        except Exception as error:
            popup['phase'] = 'error'
            popup['message'] = str(error)[:90] if isinstance(error, ValueError) else 'Spool lookup failed'
        else:
            popup['phase'] = 'writing'
            popup['message'] = 'Assigning to ' + self._mmu_gate_label(popup['operation'].gate)
        self._nfc_gate_draw()
        self.lcd.update()

    def _nfc_gate_input(self, event):
        if self._display_activity():
            return
        popup = self._nfc_gate_popup
        if event.kind == 'rotate' and popup['phase'] == 'choose':
            rows, _, _ = self._nfc_gate_choices()
            delta = abs(event.value) * (1 if event.value < 0 else -1)
            popup['selection'] = max(0, min(len(rows) - 1, popup['selection'] + delta))
            self._nfc_gate_draw()
        elif event.kind == 'press':
            if popup['phase'] != 'choose' or popup['selection'] == 0:
                self._nfc_gate_close()
                return
            try:
                # Select the operation displayed to the user; MMUSession.start
                # revalidates the fingerprint and dispatch guard after lookup.
                popup['operation'] = popup['operations'][popup['selection']]
                popup['future'] = self.pd.nfc_lookup_spool(popup['uid'])
                popup['phase'] = 'checking'
                popup['message'] = 'Checking spool tag...'
                popup['future'].add_done_callback(
                    lambda future: self._queue_nfc_ui_event('nfc_gate_verify'))
            except Exception:
                popup['phase'], popup['message'] = 'error', 'Gate assignment unavailable'
            self._nfc_gate_draw()
        else:
            return
        self.lcd.update()

    def _nfc_gate_tick(self):
        popup = getattr(self, '_nfc_gate_popup', None)
        if not popup or self.checkkey != self.NFCGateMenu:
            return False
        self._update_ui_state()
        for name in ('bed_mesh', 'screws_tilt', 'probe_wizard', 'mmu_session'):
            getattr(self.pd, name).update()
        self._focus_tick_quiet()
        if self.pd.state.epoch != popup['epoch'] or not self.pd.state.ready:
            self._nfc_gate_close()
            return True
        if popup['phase'] == 'writing':
            session = self.pd.mmu_session
            if session.operation != popup['operation']:
                popup['phase'], popup['message'] = 'error', 'MMU operation changed'
            elif session.phase in ('complete', 'error'):
                popup['phase'] = session.phase
                popup['message'] = session.message
            else:
                return True
            self._nfc_gate_draw()
            self.lcd.update()
        return True  # No underlying menu redraw may cover this prompt.

    def _nfc_gate_close(self):
        popup = getattr(self, '_nfc_gate_popup', None)
        if not popup:
            return
        future = popup.get('future')
        if future is not None and popup['phase'] == 'checking':
            future.cancel()
        self._nfc_gate_popup = None
        if self.checkkey != self.NFCGateMenu:
            return
        self.checkkey = popup['origin']
        self._list_render = None
        self._maintenance_frame = None
        self._info_render_scroll = None
        self._mmu_canvas_page = None
        if self.pd.state.epoch != popup['epoch'] or not self.pd.state.ready:
            self.checkkey = self.RecoveryScreen if self.pd.connection_error else self.MainMenu
        self._redraw_current_screen()
        self.lcd.update()
