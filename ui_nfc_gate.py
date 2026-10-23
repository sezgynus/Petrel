"""Global NFC spool-to-gate prompt, using the existing guarded MMU session."""
from lcd_resources import ICON_SPOOL
from spool_view import SpoolView
import time


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
                rows.append((label, ICON_SPOOL, None, None))
                operations.append(operation)
        return rows, operations, reason

    @staticmethod
    def _nfc_gate_color(spool):
        """RGB888 Spoolman HEX to the same RGB565 used by shared MMU reels."""
        if not spool.colors:
            return 0x8410
        rgb = int(spool.colors[0], 16)
        return ((rgb >> 19) & 31) << 11 | ((rgb >> 10) & 63) << 5 | ((rgb >> 3) & 31)

    def _nfc_gate_draw(self):
        """DWIN-native, four-lane gate selector; no duplicate spool artwork.

        The five spools are ordinary SpoolView instances, exactly as used on
        the MMU dashboard. Each gate's live ID is a caption, never an invented
        remaining percentage. A selection moves the colored reel and its
        identification card together; only a confirmed MMU readback lands it.
        """
        popup = self._nfc_gate_popup
        spool = popup['spool']
        phase = popup['phase']
        if phase == 'choose':
            _, operations, reason = self._nfc_gate_choices()
            popup['operations'] = operations
            popup['reason'] = reason
            popup['selection'] = max(0, min(popup['selection'], len(operations) - 1))
        else:
            operations = popup.get('operations')
            if operations is None:  # Documentation fixture / restored overlay.
                _, operations, reason = self._nfc_gate_choices()
                popup['operations'], popup['reason'] = operations, reason
        operations = popup['operations']
        gates = [(index, op.gate) for index, op in enumerate(operations)
                 if op is not None]
        choice = popup['selection']
        if phase != 'choose' and popup.get('operation') is not None:
            choice = next((index for index, op in enumerate(operations)
                           if op is not None and op.gate == popup['operation'].gate),
                          choice)
        page = max(0, choice - 1) // 4 if choice else 0
        visible = gates[page * 4:page * 4 + 4]
        if not visible and gates:
            visible = gates[:4]
        count = len(visible)
        spacing = 64
        left = (272 - (42 + spacing * (count - 1))) // 2 if count else 115
        positions = [(index, gate, left + slot * spacing)
                     for slot, (index, gate) in enumerate(visible)]
        selected = next((item for item in positions if item[0] == choice),
                        positions[0] if positions else None)
        spool_x = selected[2] if selected else 115
        top_y = (228 if phase in ('choose', 'checking', 'error') else
                 267 if phase == 'writing' else 315)
        reel_y = popup.get('spool_y', top_y) if phase in ('writing', 'complete') else top_y

        lcd = self.lcd
        bg, edge, muted = 0x2125, 0x5AEB, 0x6B4D
        self.Clear_Popup_Area()
        self.Draw_Title('Spool #%d: choose gate' % spool.id, back=True)
        self._draw_header_back(phase != 'choose' or popup['selection'] == 0)
        lcd.draw_rectangle(1, bg, 8, 60, 263, 429)
        lcd.draw_rectangle(0, edge, 8, 60, 263, 429)
        lcd.draw_text(False, False, lcd.font6x12, lcd.Color_White, bg,
                      18, 72, 'NFC SPOOL  #%d' % spool.id)
        lcd.draw_line(edge, 18, 92, 253, 92)

        # The readable identification card tracks the selected reel. Clamp
        # the card, not its underlying logical position, at the LCD edges.
        card_x = max(12, min(84, spool_x - 72))
        lcd.draw_rectangle(1, 0x2967, card_x, 109, card_x + 176, 202)
        lcd.draw_rectangle(0, edge, card_x, 109, card_x + 176, 202)
        def info(text, y):
            lcd.draw_text(False, False, lcd.font6x12, lcd.Color_White,
                          0x2967, card_x + 8, y, str(text)[:26])
        info(spool.vendor, 120)
        for line, y in zip(self._spool_lines(spool.name, width=26, limit=2),
                           (141, 155)):
            info(line, y)
        info('%s  /  #%d' % (spool.material, spool.id), 176)
        if spool.colors:
            for index, code in enumerate(spool.colors[:5]):
                rgb = int(code, 16)
                color = ((rgb >> 19) & 31) << 11 | ((rgb >> 10) & 63) << 5 | ((rgb >> 3) & 31)
                lcd.draw_rectangle(1, color, card_x + 137 + index * 6, 180,
                                   card_x + 142 + index * 6, 191)

        if count:
            lcd.draw_text(False, False, lcd.font6x12, muted, bg,
                          18, 290, 'Rotate encoder to choose gate')
        state = self.pd.mmu_session.state
        for index, gate, x in positions:
            focused = index == choice
            if focused and phase == 'choose':
                lcd.draw_rectangle(0, lcd.Select_Color, x - 5, 308, x + 46, 375)
            # An unassigned destination is still drawn with the real wooden
            # flanges and shared filament body, simply in a muted color.
            SpoolView(lcd, x, 315, 42, color=muted,
                      remaining_percent=None, background=bg,
                      label_width=0).draw()
            label = 'G%d' % gate
            lcd.draw_text(False, False, lcd.font8x16,
                          lcd.Color_White if focused else muted, bg,
                          x + 21 - 4 * len(label), 374, label)
            old = state.spool_ids[gate] if state and gate < len(state.spool_ids) else None
            caption = '#%d' % old if old is not None and old > 0 else 'Empty'
            lcd.draw_text(False, False, lcd.font6x12, muted, bg,
                          x + 21 - 3 * len(caption[:9]), 398, caption[:9])
        if count:
            lcd.draw_line(edge, spool_x + 21, min(reel_y + 54, 308),
                          spool_x + 21, 309)
        # Draw the moving/landing reel last: it covers the ghost destination.
        SpoolView(lcd, spool_x, reel_y, 42, color=self._nfc_gate_color(spool),
                  remaining_percent=None, background=bg, label_width=0).draw()

        if phase == 'choose':
            message = ('Press to assign  /  Back to cancel' if count else
                       popup.get('reason', 'MMU unavailable'))
        elif phase == 'checking':
            message = 'Checking spool tag...'
        elif phase == 'writing':
            message = popup['message']
        elif phase == 'complete':
            message = 'Assigned: ' + popup['message']
        else:
            message = popup['message']
        for i, line in enumerate(self._spool_lines(message, width=40, limit=2)):
            lcd.draw_text(False, False, lcd.font6x12, lcd.Color_White, bg,
                          16, 436 + 16 * i, line)
        if count and len(gates) > 4:
            lcd.draw_text(False, False, lcd.font6x12, muted, bg,
                          193, 72, '%d/%d' % (page + 1, (len(gates) + 3) // 4))

    @staticmethod
    def _nfc_gate_begin_motion(popup, target):
        popup['motion_from'] = popup.get('spool_y', 228)
        popup['motion_to'] = target
        popup['motion_started'] = time.monotonic()

    def _nfc_gate_motion_tick(self, popup):
        started = popup.get('motion_started')
        if started is None:
            return
        fraction = min(1.0, max(0.0, (time.monotonic() - started) / 0.32))
        smooth = 1.0 - (1.0 - fraction) ** 2
        y = round(popup['motion_from'] +
                  (popup['motion_to'] - popup['motion_from']) * smooth)
        if y != popup.get('spool_y'):
            popup['spool_y'] = y
            self._nfc_gate_draw()
            self.lcd.update()
        if fraction >= 1.0:
            popup.pop('motion_started', None)

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
            self._nfc_gate_begin_motion(popup, 268)
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
        if popup['phase'] == 'checking' and popup['future'].done():
            self._nfc_gate_verify()
            return True
        if popup['phase'] == 'writing':
            session = self.pd.mmu_session
            if session.operation != popup['operation']:
                popup['phase'], popup['message'] = 'error', 'MMU operation changed'
            elif session.phase in ('complete', 'error'):
                popup['phase'] = session.phase
                popup['message'] = session.message
                if session.phase == 'complete':
                    self._nfc_gate_begin_motion(popup, 315)
                else:
                    popup.pop('motion_started', None)
                    popup.pop('spool_y', None)
            else:
                self._nfc_gate_motion_tick(popup)
                return True
            self._nfc_gate_draw()
            self.lcd.update()
        if popup['phase'] == 'complete':
            self._nfc_gate_motion_tick(popup)
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
            if (self.checkkey == self.PowerConfirm
                    and getattr(self, '_power_origin', None) == self.NFCGateMenu):
                self._power_origin = popup['origin']
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
