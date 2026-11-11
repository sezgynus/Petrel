"""Global NFC spool-to-gate prompt, using the existing guarded MMU session."""
from petrel.artwork.resources import ICON_SPOOL
from petrel.features.spoolman.spool_view import SpoolView
from petrel.ui.theme import AXIS_HOMED_COLOR, AXIS_UNKNOWN_COLOR
import math
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
        if self._closed:
            return
        if spool is None:
            self._rfid_buzzer_feedback()
            return
        self._event_buzzer_melody('NFC_SPOOL_MATCH')
        if (not self._uart_online or self._closed or getattr(self, '_boot_active', False)
                or getattr(self, '_nfc_share_popup', None)
                or self.checkkey == self.PowerConfirm
                or getattr(self, '_power_hold_started', None) is not None):
            return
        existing = getattr(self, '_nfc_gate_popup', None)
        if existing and existing['phase'] in ('checking', 'writing'):
            return
        self._update_ui_state()
        live = self.pd.subscription.snapshot()['status']
        if (self.pd.status in ('printing', 'paused', 'pausing')
                or live['print_stats']['state'] in ('printing', 'paused', 'pausing')
                or live.get('virtual_sdcard', {}).get('is_active') is True):
            return  # A background NFC scan must never take focus from Print.
        self._display_activity()
        # The home MMU percentage belongs to a gate, not directly to a
        # Spoolman ID. Resolve the scanned spool once against Happy Hare's
        # current gate map; retain that single snapshot for the popup.
        percent = spool.remaining_percent
        if percent is None:
            percent = self._nfc_gate_snapshot_percent(
                spool.id, self.pd.mmu_session.state, self.pd.mmu)
        self._nfc_gate_popup = {
            'uid': uid, 'spool': spool, 'remaining_percent': percent,
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
                                                values=(popup['spool'].id, *popup['spool'].assignment))
                except ValueError as error:
                    reason = str(error)
                    continue
                old = state.spool_ids[gate]
                label = self._mmu_gate_label(gate)
                label += '  #' + str(old) if old is not None and old > 0 else '  Empty'
                rows.append((label, ICON_SPOOL, None, None))
                operations.append(operation)
        return rows, operations, reason

    # GIF reference: horizontal travel 7 x 50ms, landing ~10 x 60ms.
    # The GIF's sample positions follow the cosine ease-in-out curve.
    GATE_TRAVEL_SECONDS = .35
    GATE_LANDING_SECONDS = .60
    GATE_ANIMATION_INTERVAL = .05
    GATE_BG = 0x2125
    GATE_PANEL = 0x2967
    GATE_REEL_TOP = 234
    GATE_GHOST_TOP = 326
    GATE_CARD_TOP = 132
    GATE_CARD_WIDTH = 128
    GATE_CARD_HEIGHT = 56
    GATE_REEL_WIDTH = 42
    GATE_REEL_HEIGHT = 52

    @staticmethod
    def _nfc_gate_snapshot_percent(spool_id, state, mmu):
        """Freeze the Home/Happy Hare fill for this *spool*, not selected gate.

        HH publishes percentages per gate. Unmounted/unknown spools must not
        inherit another gate's percentage as the reel moves across the slots.
        """
        if state is None or not isinstance(mmu, dict):
            return None
        percentages = mmu.get('remaining_percent', ())
        if not isinstance(percentages, (tuple, list)):
            return None
        for gate, assigned in enumerate(state.spool_ids):
            if assigned != spool_id or gate >= len(percentages):
                continue
            if gate < len(state.gate_status) and state.gate_status[gate] == 0:
                return 0  # Same empty-gate policy as Home/MMU.
            value = percentages[gate]
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value)):
                return max(0, min(100, int(round(value))))
        return None

    @staticmethod
    def _nfc_gate_color(spool):
        """RGB888 Spoolman HEX to the shared MMU RGB565 color."""
        if not spool.colors:
            return 0x8410
        rgb = int(spool.colors[0], 16)
        return ((rgb >> 19) & 31) << 11 | ((rgb >> 10) & 63) << 5 | ((rgb >> 3) & 31)

    @staticmethod
    def _nfc_gate_ease(progress):
        fraction = max(0., min(1., progress))
        return .5 - .5 * math.cos(math.pi * fraction)

    @staticmethod
    def _nfc_gate_card_x(spool_x):
        # Keep the compact text panel entirely inside the 272px viewport.
        return max(8, min(136, spool_x + 21 - 64))

    # The original GIF links the rounded identity card to the reel, then
    # links the reel to the selected gate with a subtle cyan terminal dot.
    # The lines live OUTSIDE the sprites' 0x09 source rectangles so every
    # animation frame can erase/redraw just two thin lines, never an icon.
    GATE_LINK_COLOR = 0x5AEB
    GATE_LINK_TIP_Y = GATE_GHOST_TOP - 13

    def _nfc_gate_clear_links(self, popup):
        lcd = self.lcd
        for x0, y0, x1, y1 in popup.pop('link_segments', ()):
            lcd.draw_line(self.GATE_BG, x0, y0, x1, y1)
        tip = popup.pop('link_tip', None)
        if tip is not None:
            lcd.draw_rectangle(1, self.GATE_BG, tip - 2,
                               self.GATE_LINK_TIP_Y - 2, tip + 2,
                               self.GATE_LINK_TIP_Y + 2)

    def _nfc_gate_draw_links(self, popup):
        """Connect card → reel → target gate using only small DWIN primitives."""
        positions = popup.get('positions') or {}
        if not positions:
            return
        x, y = popup['sprite_x'], popup['sprite_y']
        reel_center = x + self.GATE_REEL_WIDTH // 2
        card_center = popup['card_x'] + self.GATE_CARD_WIDTH // 2
        upper = (card_center, self.GATE_CARD_TOP + self.GATE_CARD_HEIGHT + 4,
                 reel_center, y - 5)
        segments = [upper]
        target = positions.get(popup['selection'])
        if target is None:
            target = next(iter(positions.values()))
        target_center = target + self.GATE_REEL_WIDTH // 2
        lower_start = y + self.GATE_REEL_HEIGHT + 3
        # During the 600ms landing this stem naturally shortens, then
        # disappears rather than crossing the descending reel or gate artwork.
        if lower_start < self.GATE_LINK_TIP_Y - 2:
            segments.append((reel_center, lower_start,
                             target_center, self.GATE_LINK_TIP_Y - 2))
            popup['link_tip'] = target_center
        popup['link_segments'] = tuple(segments)
        for coords in segments:
            self.lcd.draw_line(self.GATE_LINK_COLOR, *coords)
        if 'link_tip' in popup:
            cx = popup['link_tip']
            self.lcd.draw_rectangle(1, AXIS_HOMED_COLOR,
                                    cx - 2, self.GATE_LINK_TIP_Y - 2,
                                    cx + 2, self.GATE_LINK_TIP_Y + 2)

    def _nfc_gate_draw_focus(self, previous=None):
        """Recolor only tiny gate footers / header focus, never the reels."""
        popup = self._nfc_gate_popup
        lcd = self.lcd
        positions = popup.get('positions', {})
        for index in (previous, popup['selection']):
            if index is None or index not in positions:
                continue
            x = positions[index]
            lcd.draw_rectangle(1, AXIS_HOMED_COLOR if index == popup['selection']
                               else self.GATE_BG, x + 4, 415, x + 37, 418)
        self._draw_header_back(popup['selection'] == 0)

    def _nfc_gate_draw_status(self):
        popup = self._nfc_gate_popup
        lcd = self.lcd
        phase = popup['phase']
        # No encoder instructions: the reel and four gates are self-explanatory.
        if phase == 'choose' and popup.get('positions'):
            message = ''
        elif phase == 'choose':
            message = popup.get('reason', 'MMU unavailable')
        elif phase == 'checking':
            message = 'Checking spool tag...'
        elif phase == 'writing':
            message = popup['message']
        elif phase == 'complete':
            message = 'Assigned: ' + popup['message']
        else:
            message = popup['message']
        bg = self.GATE_PANEL if message else self.GATE_BG
        lcd.draw_rectangle(1, bg, 8, 430, 263, 468)
        if message:
            lcd.draw_rectangle(0, AXIS_UNKNOWN_COLOR, 8, 430, 263, 468)
            for i, line in enumerate(self._spool_lines(message, width=39, limit=2)):
                lcd.draw_text(False, False, lcd.font6x12,
                              AXIS_HOMED_COLOR if phase == 'complete' else lcd.Color_White,
                              bg, 17, 438 + i * 14, line)

    def _nfc_gate_draw(self):
        """Paint a scene once; subsequent selection and motion use native 0x09."""
        popup = self._nfc_gate_popup
        if popup['phase'] == 'choose' or 'operations' not in popup:
            _, operations, reason = self._nfc_gate_choices()
            popup['operations'], popup['reason'] = operations, reason
            popup['selection'] = max(0, min(popup['selection'], len(operations) - 1))
        operations = popup['operations']
        gates = [(index, op.gate) for index, op in enumerate(operations)
                 if op is not None]
        selection = popup['selection']
        if popup.get('operation') is not None and popup['phase'] != 'choose':
            selection = next((index for index, op in enumerate(operations)
                              if op is not None and op.gate == popup['operation'].gate),
                             selection)
        page = max(0, selection - 1) // 4 if selection else 0
        if popup.get('drawn_page') == page and popup.get('drawn_lcd') == id(self.lcd):
            self._nfc_gate_draw_status()
            return

        visible = gates[page * 4:page * 4 + 4]
        if not visible and gates:
            visible = gates[:4]
        count = len(visible)
        left = (272 - (42 + 64 * (count - 1))) // 2 if count else 115
        positions = {index: left + slot * 64
                     for slot, (index, _) in enumerate(visible)}
        popup['positions'] = positions
        x = positions.get(selection, next(iter(positions.values()), 115))
        y = self.GATE_GHOST_TOP if popup['phase'] == 'complete' else self.GATE_REEL_TOP
        popup['sprite_x'], popup['sprite_y'] = x, y
        popup['card_x'] = self._nfc_gate_card_x(x)
        popup.pop('link_segments', None)
        popup.pop('link_tip', None)
        popup['drawn_page'], popup['drawn_lcd'] = page, id(self.lcd)
        popup.pop('motion', None)
        lcd = self.lcd
        bg, panel = self.GATE_BG, self.GATE_PANEL

        self.Clear_Popup_Area()
        # 0x09 fills newly exposed pixels with graphite. Prepaint the same
        # graphite behind both moving bands once to prevent wake/trail stripes.
        lcd.draw_rectangle(1, bg, 0, 31, 271, 429)
        self.Draw_Title('ASSIGN FILAMENT', back=True)
        lcd.draw_rectangle(1, panel, 8, 58, 263, 96)
        lcd.draw_rectangle(0, AXIS_UNKNOWN_COLOR, 8, 58, 263, 96)
        lcd.draw_text(False, False, lcd.font8x16, lcd.Color_White, panel,
                      17, 65, 'SPOOLMAN  /  MMU')
        lcd.draw_text(False, False, lcd.font6x12, AXIS_HOMED_COLOR, bg,
                      15, 111, 'NFC TAG READ   #%d' % popup['spool'].id)
        if len(gates) > 4:
            lcd.draw_text(False, False, lcd.font6x12, AXIS_HOMED_COLOR, bg,
                          195, 111, '%d/%d' % (page + 1, (len(gates) + 3) // 4))

        state = self.pd.mmu_session.state
        for index, gate in visible:
            gx = positions[index]
            SpoolView(lcd, gx, self.GATE_GHOST_TOP, color=0x6B4D,
                      remaining_percent=None, background=bg, label_width=0).draw()
            label = 'G%d' % gate
            lcd.draw_text(False, False, lcd.font8x16,
                          lcd.Color_White if index == selection else AXIS_UNKNOWN_COLOR,
                          bg, gx + 21 - 4 * len(label), 381, label)
            old = state.spool_ids[gate] if state and gate < len(state.spool_ids) else None
            assigned = '#%d' % old if old is not None and old > 0 else 'Empty'
            lcd.draw_text(False, False, lcd.font6x12, AXIS_UNKNOWN_COLOR, bg,
                          gx + 21 - 3 * len(assigned[:7]), 398, assigned[:7])
        if popup['phase'] != 'complete':
            SpoolView(lcd, x, y, color=self._nfc_gate_color(popup['spool']),
                      remaining_percent=popup.get('remaining_percent'),
                      background=bg, label_width=42).draw()
        else:
            # Documentation "complete" scene starts with the reel already landed.
            lcd.draw_rectangle(1, bg, x, y, x + 41, y + 51)
            SpoolView(lcd, x, y, color=self._nfc_gate_color(popup['spool']),
                      remaining_percent=popup.get('remaining_percent'),
                      background=bg, label_width=42).draw()

        self._nfc_gate_draw_card(popup['card_x'])
        self._nfc_gate_draw_links(popup)
        self._nfc_gate_draw_focus()
        self._nfc_gate_draw_status()

    def _nfc_gate_draw_card(self, x):
        """GIF-style rounded info capsule, painted once and shifted via 0x09."""
        lcd = self.lcd
        spool = self._nfc_gate_popup['spool']
        y = self.GATE_CARD_TOP
        width, height = self.GATE_CARD_WIDTH, self.GATE_CARD_HEIGHT
        radius = 9
        bg, border = self.GATE_PANEL, AXIS_UNKNOWN_COLOR

        # Fill as a pill-shaped panel without adding any atlas/JPEG icons.
        # Only the first presentation needs these inexpensive primitives;
        # every subsequent horizontal frame moves its existing pixels.
        lcd.draw_rectangle(1, bg, x + radius, y,
                           x + width - radius - 1, y + height - 1)
        lcd.draw_rectangle(1, bg, x, y + radius,
                           x + width - 1, y + height - radius - 1)
        arc = []
        for dy in range(radius):
            inset = int(math.ceil(radius -
                         math.sqrt(max(0., radius ** 2 - (radius - dy - .5) ** 2))))
            arc.append(inset)
            lcd.draw_rectangle(1, bg, x + inset, y + dy,
                               x + width - inset - 1, y + dy)
            lcd.draw_rectangle(1, bg, x + inset, y + height - dy - 1,
                               x + width - inset - 1, y + height - dy - 1)
        # Pixel-accurate rounded outline, a single native polyline command.
        points = [(x + arc[0], y), (x + width - arc[0] - 1, y)]
        points.extend((x + width - inset - 1, y + dy)
                      for dy, inset in enumerate(arc))
        points.append((x + width - 1, y + radius))
        points.append((x + width - 1, y + height - radius - 1))
        points.extend((x + width - inset - 1, y + height - dy - 1)
                      for dy, inset in reversed(tuple(enumerate(arc))))
        points += [(x + arc[0], y + height - 1)]
        points.extend((x + inset, y + height - dy - 1)
                      for dy, inset in enumerate(arc))
        points.append((x, y + height - radius - 1))
        points.append((x, y + radius))
        points.extend((x + inset, y + dy)
                      for dy, inset in reversed(tuple(enumerate(arc))))
        lcd.draw_polyline(border, points)

        # Rounded filament-color side accent from the original GIF.
        color = self._nfc_gate_color(spool)
        lcd.draw_rectangle(1, color, x + 7, y + 9, x + 10, y + height - 10)
        lcd.draw_rectangle(1, color, x + 8, y + 7, x + 9, y + 8)
        lcd.draw_rectangle(1, color, x + 8, y + height - 9,
                           x + 9, y + height - 8)

        # Identity hierarchy follows the reference: manufacturer, colored
        # filament name, muted material/ID. Use short panel-native strings.
        lcd.draw_text(False, False, lcd.font8x16, lcd.Color_White, bg,
                      x + 17, y + 5, spool.vendor[:13])
        lcd.draw_text(False, False, lcd.font6x12, color, bg,
                      x + 17, y + 25, spool.name[:17])
        lcd.draw_text(False, False, lcd.font6x12, AXIS_UNKNOWN_COLOR, bg,
                      x + 17, y + 41,
                      ('%s  #%d' % (spool.material, spool.id))[:17])

    def _nfc_gate_move(self, popup, x=None, y=None):
        """Shift an isolated sprite in framebuffer, not a redrawn icon.

        Mode 1 clears the exposed strip to graphite. Movement rectangles include
        exactly the old and new sprite footprint, avoiding static UI contents.
        """
        lcd = self.lcd
        bg = self.GATE_BG
        old_x, old_y = popup['sprite_x'], popup['sprite_y']
        changed = ((x is not None and x != old_x)
                   or (y is not None and y != old_y))
        if changed:
            self._nfc_gate_clear_links(popup)
        if x is not None and x != old_x:
            delta = x - old_x
            lcd.move_area(1, 1 if delta > 0 else 0, abs(delta), bg,
                          min(x, old_x), old_y,
                          max(x, old_x) + self.GATE_REEL_WIDTH - 1,
                          old_y + self.GATE_REEL_HEIGHT - 1)
            old_card = popup['card_x']
            card = self._nfc_gate_card_x(x)
            if card != old_card:
                delta = card - old_card
                lcd.move_area(1, 1 if delta > 0 else 0, abs(delta), bg,
                              min(card, old_card), self.GATE_CARD_TOP,
                              max(card, old_card) + self.GATE_CARD_WIDTH - 1,
                              self.GATE_CARD_TOP + self.GATE_CARD_HEIGHT - 1)
            popup['sprite_x'], popup['card_x'] = x, card
        if y is not None and y != old_y:
            delta = y - old_y
            lcd.move_area(1, 3 if delta > 0 else 2, abs(delta), bg,
                          popup['sprite_x'], min(old_y, y),
                          popup['sprite_x'] + self.GATE_REEL_WIDTH - 1,
                          max(old_y, y) + self.GATE_REEL_HEIGHT - 1)
            popup['sprite_y'] = y
        if changed:
            self._nfc_gate_draw_links(popup)
        lcd.update()

    def _nfc_gate_animate(self, popup, axis, target, seconds, *, now=None):
        now = time.monotonic() if now is None else now
        origin = popup['sprite_x' if axis == 'x' else 'sprite_y']
        if origin == target:
            popup.pop('motion', None)
            return
        popup['motion'] = {'axis': axis, 'from': origin, 'to': target,
                           'start': now, 'duration': seconds}
        loop = getattr(self, '_loop', None)
        if loop is not None:
            loop.cap_interval(self.GATE_ANIMATION_INTERVAL)

    def _nfc_gate_select(self, selection):
        popup = self._nfc_gate_popup
        old = popup['selection']
        if selection == old:
            return
        popup['selection'] = selection
        page = max(0, selection - 1) // 4 if selection else 0
        if page != popup.get('drawn_page'):
            self._nfc_gate_draw()
        else:
            self._nfc_gate_draw_focus(previous=old)
            # Back stays in the header; visible reel sits above the first gate.
            target = popup['positions'].get(selection)
            if target is not None:
                self._nfc_gate_animate(popup, 'x', target, self.GATE_TRAVEL_SECONDS)
        self.lcd.update()

    def _nfc_gate_motion_tick(self, popup, *, now=None):
        motion = popup.get('motion')
        if motion is None:
            return False
        now = time.monotonic() if now is None else now
        progress = (now - motion['start']) / motion['duration']
        position = round(motion['from'] + (motion['to'] - motion['from'])
                         * self._nfc_gate_ease(progress))
        if motion['axis'] == 'x':
            self._nfc_gate_move(popup, x=position)
        else:
            self._nfc_gate_move(popup, y=position)
        if progress >= 1.:
            popup.pop('motion', None)
            pending = popup.pop('pending_y', None)
            if pending is not None:
                self._nfc_gate_start_vertical(popup, pending, now=now)
            else:
                loop = getattr(self, '_loop', None)
                if loop is not None:
                    loop.set_interval(.5)
        return True

    def _nfc_gate_start_vertical(self, popup, target, *, now=None):
        # An in-flight horizontal motion completes before descent. A falling
        # reel cannot cross the other gate images or their labels.
        if popup.get('motion', {}).get('axis') == 'x':
            popup['pending_y'] = target
            return
        if target == self.GATE_GHOST_TOP:
            # Hide only the destination's ghost exactly once, before descending.
            # Later frames are 0x09 moves; neither the gate row nor its labels
            # are recreated during animation.
            x = popup['sprite_x']
            self.lcd.draw_rectangle(1, self.GATE_BG, x, self.GATE_GHOST_TOP,
                                    x + 41, self.GATE_GHOST_TOP + 51)
        self._nfc_gate_animate(popup, 'y', target,
                               self.GATE_LANDING_SECONDS, now=now)

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
            # Keep the reel hovering during verification; the GIF has one
            # continuous ~600ms descent, only after confirmed MMU readback.
            popup['message'] = 'Assigning to ' + self._mmu_gate_label(popup['operation'].gate)
        self._nfc_gate_draw()
        self.lcd.update()

    def _nfc_gate_input(self, event):
        self._update_ui_state()
        if self.pd.status in ('printing', 'paused', 'pausing'):
            self._nfc_gate_close()
            self.Goto_PrintProcess()
            return
        if self._display_activity():
            return
        # NFC gate input branches off before the normal UI's shared buzzer
        # feedback call. Give rotary detents and encoder presses the same
        # configured sounds as every other menu (including Back/confirm).
        if event.kind in ('rotate', 'press'):
            self._buzzer_feedback(event.kind)
        popup = self._nfc_gate_popup
        if event.kind == 'rotate' and popup['phase'] == 'choose':
            delta = abs(event.value) * (1 if event.value < 0 else -1)
            self._nfc_gate_select(max(0, min(len(popup['operations']) - 1,
                                          popup['selection'] + delta)))
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
        now = time.monotonic()
        self._nfc_gate_motion_tick(popup, now=now)
        # At 50ms animation cadence, only 0x09 is transmitted. Keep the
        # MMU/subscription poll at the usual 500ms rather than 20Hz.
        if now < popup.get('next_state_poll', 0):
            return True
        popup['next_state_poll'] = now + .5
        self._update_ui_state()
        for name in ('bed_mesh', 'screws_tilt', 'probe_wizard', 'mmu_session'):
            getattr(self.pd, name).update()
        self._focus_tick_quiet()
        if self.pd.status in ('printing', 'paused', 'pausing'):
            # An idle gate-selection popup is not a print-time navigation path.
            self._nfc_gate_close()
            self.Goto_PrintProcess()
            return True
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
                self._nfc_gate_start_vertical(popup, self.GATE_REEL_TOP)
            elif session.phase in ('complete', 'error'):
                popup['phase'], popup['message'] = session.phase, session.message
                self._nfc_gate_start_vertical(popup,
                    self.GATE_GHOST_TOP if session.phase == 'complete'
                    else self.GATE_REEL_TOP)
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
        if popup.get('motion') and getattr(self, '_loop', None) is not None:
            self._loop.set_interval(.5)
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
