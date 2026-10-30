"""MMU status, spool overview, filament path and overview animation."""
from petrel.features.spoolman.spool_view import SpoolView
from petrel.features.mmu.filament_view import MMUFilamentView, filament_color
from petrel.ui.numbers import fixed, compact


class MMUOverviewMixin:
    def _mmu_temperature_text(self):
        heater = self.pd.capabilities.active_hotend
        if heater is None:
            return '-- C'
        raw = self.pd.state.status.get(heater.name,{})
        text = fixed(raw.get('temperature',0),1)+'/'+compact(raw.get('target',0))+' C'
        if len(text)>18:
            temps = self.pd.thermalManager['temp_hotend'][0]
            return '%d/%d C'%(temps['celsius'],temps['target'])
        return text

    @staticmethod
    def _rgb565(rgb):
        r, g, b = (int(round(max(0.0, min(1.0, value)) * 31)) for value in rgb)
        # Green has 6 bits in RGB565.
        g = int(round(max(0.0, min(1.0, rgb[1])) * 63))
        return (r << 11) | (g << 5) | b

    def Draw_MMU_Status(self):
        mmu = self.pd.mmu
        if not mmu:
            return
        count = mmu['num_gates']
        active = mmu['gate']
        # Fill nearly the entire strip above the main menu icons.
        left, top, width = 8, 39, 256
        gap = 5 if count <= 4 else 2 if count <= 8 else 1
        if count > 32:
            gap = 0
        slot = max(1, min(60, (width - gap * (count - 1)) // count))
        total = slot * count + gap * (count - 1)
        start = left + max(0, (width - total) // 2)
        layout = (id(self.lcd), count)
        if layout != getattr(self, '_home_mmu_layout', None):
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 4, 31, 268, 125)
            self._home_mmu_layout = layout
            self._home_mmu_title = None
            self._home_mmu_gates = {}
            self._home_spool_views = {}
        title = str(mmu.get('name') or 'MMU')[:22]
        title_x = max(4, (self.lcd.DWIN_WIDTH - 6 * len(title)) // 2)
        if title != self._home_mmu_title:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 4, 31, 268, 44)
            self._home_mmu_title = title
            self.lcd.draw_text(False, True, self.lcd.font6x12,
                             self.lcd.Color_White, self.lcd.Color_Bg_Black,
                             title_x, 32, title)

        percentages = mmu.get('remaining_percent', ())
        for gate in range(count):
            x = start + gate * (slot + gap)
            status = mmu['gate_status'][gate]
            color = self._rgb565(mmu['gate_color_rgb'][gate]) if status > 0 else 0x8410
            cx = x + slot // 2
            reel_w = min(max(8, int(slot * 0.70)), max(1, slot - 2))
            reel_x = x + (slot - reel_w) // 2
            percent = percentages[gate] if gate < len(percentages) else None
            if status == 0:
                percent = 0
            cache = self._home_mmu_gates.setdefault(gate, {})
            spool = self._home_spool_views.get(gate)
            if spool is None:
                spool = self._home_spool_views[gate] = SpoolView(
                    self.lcd, reel_x, top + 7, reel_w,
                    background=self.lcd.Color_Bg_Black, label_width=slot)
            spool.color = color
            spool.remaining_percent = percent
            spool.draw()

            label = str(gate)
            label_w = max(1, min(38, slot - 2 if slot > 2 else slot))
            lx0, lx1 = cx - label_w // 2, cx + label_w // 2
            exit_leds = mmu.get('exit_led_rgb', ())
            led_color = None
            if gate < len(exit_leds):
                rgb = exit_leds[gate]
                peak = max(rgb)
                # Mirror the LED hue, not its physical brightness.  Happy Hare
                # may deliberately drive a color at low intensity (e.g. red
                # at 0.1), which is too dark on the LCD if copied literally.
                normalized_rgb = (tuple(channel / peak for channel in rgb)
                                  if peak > 0 else rgb)
                led_color = self._rgb565(normalized_rgb)
            active_green = 0x07E0
            indicator = led_color if led_color is not None else (
                active_green if gate == active else self.lcd.Line_Color)
            # Every lane mirrors its live Happy Hare exit LED continuously.
            # Black/off LEDs therefore render as black rather than falling back.
            label_bg = self.lcd.Color_Bg_Black
            border = self.lcd.Select_Color if gate == active else self.lcd.Line_Color
            signature = (indicator, gate == active)
            if cache.get('indicator') != signature:
                cache['indicator'] = signature
                self.lcd.draw_rectangle(1, label_bg, lx0, top + 64, lx1, top + 78)
                self.lcd.draw_rectangle(0, border, lx0, top + 64, lx1, top + 78)
                self.lcd.draw_rectangle(1, indicator, lx0+1, top + 77, max(lx0+1,lx1-1), top + 78)
                self.lcd.draw_text(False, True, self.lcd.font6x12,
                                     self.lcd.Color_White, label_bg,
                                     cx - 3 * len(label), top + 65, label)

    def _mmu_percent(self, gate):
        percentages = (self.pd.mmu or {}).get('remaining_percent', ())
        value = percentages[gate] if gate < len(percentages) else None
        return '--' if value is None else '%d%%' % value

    def _mmu_spools(self, m):
        count = min(4, m.num_gates)
        focused = self._mmu_selection - 1
        selected = focused if 0 <= focused < m.num_gates else m.tool if m.tool is not None and m.tool >= 0 else 0
        start = min((selected // 4) * 4, ((m.num_gates - 1) // 4) * 4)
        home = self.pd.mmu or {}
        colors, percentages = home.get('gate_color_rgb', ()), home.get('remaining_percent', ())
        page = (id(self.lcd), start, count)
        if page != getattr(self, '_mmu_spool_page', None):
            self._mmu_spool_page = page
            self._mmu_spool_views = {}
            self.lcd.draw_rectangle(1, 0x2125, 8, 34, 263, 131)
            for key in list(self._mmu_render):
                if key.startswith('spool'):
                    self._mmu_render.pop(key)
        for slot, tool in enumerate(range(start, min(m.num_gates, start + count))):
            gate = m.ttg_map[tool]
            valid = gate is not None and 0 <= gate < m.num_gates
            x = 14 + slot * 66
            rgb = colors[gate] if valid and gate < len(colors) else None
            color = (self._rgb565(rgb) if rgb is not None else filament_color(m.colors[gate]) if valid else 0x8410)
            self._mmu_text('spooltool%d' % slot, self._mmu_gate_label(gate), x + 9, 36, 5, small=True)
            spool = self._mmu_spool_views.get(tool)
            if spool is None:
                spool = self._mmu_spool_views[tool] = SpoolView(self.lcd, x, 51)
            spool.color = color
            spool.remaining_percent = (0 if valid and m.gate_status[gate] == 0 else
                percentages[gate] if valid and gate < len(percentages) else None)
            spool.draw()
            # Gate/LED indicators remain outside the shared spool component.
            bg = color
            key = 'spoolgate%d' % slot
            marker = (tool, gate, bg, focused == tool, m.tool == tool)
            if self._mmu_render.get(key) != marker:
                self._mmu_render[key] = marker
                self.lcd.draw_rectangle(1, bg, x, 109, x + 41, 128)
                border = 0xFFFF if focused == tool else 0x07E0 if m.tool == tool else 0x2125
                self.lcd.draw_rectangle(0, border, x, 109, x + 41, 128)
                self.lcd.draw_text(False, False, self.lcd.font6x12,
                    SpoolView._text_color(bg), bg, x + 12, 113, 'T%d' % tool)
        if m.num_gates > 4:
            self._mmu_text('gatepage', '%d/%d' % (start // 4 + 1, (m.num_gates + 3) // 4), 218, 132, 8, small=True)

    def _mmu_animation_tick(self):
        view = getattr(self, '_mmu_filament_view', None)
        state = getattr(self, '_mmu_animation_state', None)
        if view is not None and state is not None:
            if view.draw(state, active_color=self._mmu_animation_color):
                self.lcd.update()

    def _mmu_draw_overview(self, m, items):
        if m:
            self._mmu_spools(m)
            view = getattr(self, '_mmu_filament_view', None)
            if view is None:
                view = self._mmu_filament_view = MMUFilamentView(self.lcd)
            rgb = (self.pd.mmu or {}).get('gate_color_rgb', ())
            active_color = self._rgb565(rgb[m.gate]) if m.gate is not None and 0 <= m.gate < len(rgb) else None
            self._mmu_animation_state = m
            self._mmu_animation_color = active_color
            view.draw(m, active_color=active_color)
            distance = '--' if m.filament_position is None else fixed(m.filament_position,1)
            self._mmu_text('distance', 'Filament: %smm' % distance, 40, 147, 32, small=True)
            self._mmu_text('tool', self._mmu_tool_label(m.tool), 20, 184, 4, bg=view.BLOCK)
            phase = 'DISABLED' if m.enabled is not True else 'PAUSED' if m.locked else m.action
            if phase == 'Idle':
                phase = m.filament.title()
            for row in range(2):
                self._mmu_text('phase%d' % row, phase[row * 12:(row + 1) * 12], 160, 177 + row * 16, 12, small=True, color=0x07E0 if m.enabled and not m.locked else 0xFD20)
            valid = m.gate is not None and 0 <= m.gate < m.num_gates
            name = (m.names[m.gate] or '--') if valid else 'Bypass' if m.gate == -2 else '--'
            material = (m.materials[m.gate] or '--') if valid else '--'
            for row in range(2):
                self._mmu_text('name%d' % row, name[row * 16:(row + 1) * 16], 160, 231 + row * 15, 16, small=True)
            self._mmu_text('material', material, 160, 266, 16, small=True)
            self._mmu_text('mapping', '%s > %s' % (self._mmu_tool_label(m.tool), self._mmu_gate_label(m.gate)), 160, 287, 16, small=True)
            temps = self.pd.thermalManager['temp_hotend'][0]
            self._mmu_text('temperature', self._mmu_temperature_text(), 26, 396, 18, small=True)
        else:
            self._mmu_text('unavailable', 'OFFLINE' if self.pd.connection_error else 'Happy Hare unavailable', 12, 180)
        offset = m.num_gates if m else 0
        for i, (_, label, _, enabled) in enumerate(items[offset:]):
            self._mmu_row('primary%d' % i, label, '', 8 + i * 132, 428, 124,
                          self._mmu_selection == offset + i + 1, enabled)
        notice = self._mmu_notice or (self.pd.mmu_session.message if self.pd.mmu_session.phase == 'error' else m.reason if m and m.locked else '')
        for row in range(2):
            self._mmu_text('notice%d' % row, notice[row * 16:(row + 1) * 16], 160, 330 + row * 15, 16, small=True, color=0xFD20)

    def _mmu_nozzle(self, y):
        temps = self.pd.thermalManager['temp_hotend'][0]
        value = 'Nozzle '+self._mmu_temperature_text() if self.pd.HAS_HOTEND else 'Nozzle unavailable'
        self._mmu_text('nozzle', value, 12, y)

    def _mmu_path(self, m, y):
        signature = (m.filament, y)
        if self._mmu_render.get('path') == signature:
            return
        self._mmu_render['path'] = signature
        self.lcd.draw_rectangle(1, 0x2125, 12, y, 259, y + 40)
        color = 0x249F if m.filament == 'loaded' else 0x8410
        for x, name in ((14, 'GATE'), (82, 'BOWDEN'), (200, 'NOZZLE')):
            self.lcd.draw_text(False, False, self.lcd.font6x12, 0x8410, 0x2125, x, y, name)
        self.lcd.draw_line(color, 30, y + 24, 233, y + 24)
        for x in (26, 106, 229):
            self.lcd.draw_rectangle(1, color, x, y + 20, x + 7, y + 27)
