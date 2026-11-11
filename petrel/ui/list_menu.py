"""Existing display methods grouped by responsibility."""
from petrel.ui.theme import show_icon as show_theme_icon
from petrel.artwork.resources import ICON_CHECKBOX_EMPTY, ICON_CHECKBOX_CHECKED
from petrel.ui.numbers import fixed, compact, fit_decimal


class ListMenuMixin:
    def _menu_navigation(self, menu, selection, index_name, draw):
        event = self.get_encoder_state()
        if event not in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            return False
        # Coalesced detents have a single final menu position. Avoid drawing
        # each intermediate row/window on the UART owner thread.
        steps = max(1, int(getattr(self, '_menu_batch_steps', 1)))
        target = selection.now + (steps if event == self.ENCODER_DIFF_CW else -steps)
        target = max(0, min(len(self._menus[menu]), target))
        if target == selection.now:
            return True
        selection.set(target)
        bottom = getattr(self, index_name, self.MROWS)
        if selection.now > bottom:
            bottom = selection.now
        elif selection.now < bottom - self.MROWS:
            bottom = selection.now + self.MROWS
        setattr(self, index_name, max(self.MROWS, bottom))
        draw()
        self.lcd.update()
        return True

    def _menu_checkbox_painter(self, checked):
        def draw(row):
            x, y = 232, self.MBASE(row) - 3
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, x, y, x + 19, y + 19)
            show_theme_icon(self.lcd, self.ICON,
                ICON_CHECKBOX_CHECKED if checked else ICON_CHECKBOX_EMPTY, x, y)
        draw.checkbox = True
        return draw

    def _draw_list_menu(self, title, entries, selection, start=None):
        # Keep logical return index 0 for controllers; render it in the header.
        header_back = bool(entries and entries[0][0] == 'Back')
        first = 1 if header_back else 0
        # Entries: label, icon, displayed value signature, optional row painter.
        frame = (id(self.lcd), title, tuple((e[0], e[1]) for e in entries))
        old = getattr(self, '_list_render', None)
        valid = old is not None and old['frame'] == frame
        if start is None:
            start = old['start'] if valid else first
            if selection is not None:
                start = max(first, min(start, max(first, selection)), selection - self.MROWS)
        start = max(first, start)
        if selection is not None and selection >= first:
            start = max(first, min(start, selection), selection - self.MROWS)
        visible = range(start, min(len(entries), start + self.TROWS))
        previous_values = old['values'] if valid else {}
        delta = start - old['start'] if valid else 0
        if not valid or abs(delta) >= self.TROWS:
            self.Clear_Main_Window()
            self.Draw_Title(title, back=header_back)
            previous_values = {}
        elif old['selection'] != selection or delta:
            if old['selection'] is not None and old['selection'] >= first:
                self.Erase_Menu_Cursor(old['selection'] - old['start'])
            if delta:
                self.lcd.move_area(1,
                    self.DWIN_SCROLL_UP if delta > 0 else self.DWIN_SCROLL_DOWN,
                    abs(delta) * self.MLINE, self.lcd.Color_Bg_Black,
                    0, 31, 271, 348)
        values = {}
        for logical in visible:
            label, icon, value, painter = entries[logical]
            row = logical - start
            values[logical] = value
            preserved = valid and logical in range(old['start'], old['start'] + self.TROWS)
            if not preserved or logical not in previous_values or previous_values[logical] != value:
                checkbox_only = (preserved and logical in previous_values
                                 and getattr(painter, 'checkbox', False))
                if not checkbox_only:
                    self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                        16, 31 + row * self.MLINE, 271, 83 + row * self.MLINE)
                    if icon or label:
                        self.Draw_Menu_Line(row, icon, label)
                if painter is not None:
                    painter(row)
        if not valid or delta or old['selection'] != selection:
            if selection is not None and selection >= first:
                self.Draw_Menu_Cursor(selection - start)
        if header_back:
            self._draw_header_back(selection == 0)
        self._list_render = dict(frame=frame, start=start, selection=selection, values=values)

    def _draw_capability_menu(self, name, selection, bottom=None, profile=None):
        title = name.title() if profile is None else self.pd.material_preset[profile].name + ' settings'
        entries = [('Back', self.ICON_Back, None, None)]
        preset = self.pd.material_preset[profile] if profile is not None else None
        for key, label, icon in self._menus[name]:
            value, painter = None, None
            if name in ('temperature', 'tune', 'preheat'):
                if key == 'TEMP':
                    value = preset.hotend_temp if preset else self.pd.state.status[self.pd.capabilities.active_hotend.name]['target']
                elif key == 'BED':
                    value = preset.bed_temp if preset else self.pd.state.status['heater_bed']['target']
                elif key == 'FAN':
                    value = self.pd.thermalManager['fan_speed'][0]
                elif key == 'SPEED':
                    value = self.pd.feedrate_percentage
                elif key == 'ZOFF':
                    value = self.pd.BABY_Z_VAR * 100
                    painter = lambda row, v=value: self._draw_offset_value(v,self.MBASE(row),self.lcd.Color_Bg_Black)
                if key in ('TEMP','BED') and value is not None:
                    painter = lambda row, v=value: self._draw_thermal_target(v,self.MBASE(row),self.lcd.Color_Bg_Black)
                if value is not None and painter is None:
                    painter = lambda row, v=value: self._draw_menu_value(
                        str(v), self.MBASE(row), self.lcd.Color_Bg_Black,
                        self.MENU_NARROW_CELLS)
            entries.append((label, icon, value, painter))
        self._draw_list_menu(title, entries, selection.now, max(0, (bottom or self.MROWS) - self.MROWS))

    def _menu_row(self, logical):
        render = getattr(self, '_list_render', None)
        return logical - (render['start'] if render else 1)

    def _invalidate_list_row(self, row):
        """A direct editor write replaces the normal cached viewport row."""
        render = getattr(self, '_list_render', None)
        if render is not None:
            render['values'].pop(row + render['start'], None)
        return row

    def _open_thermal_editor(self, key, row, profile=None):
        # Menu selections are logical indices; drawing uses viewport rows.
        render = getattr(self, '_list_render', None)
        self._thermal_edit_row = row - (render['start'] if render else 0)
        self._invalidate_list_row(self._thermal_edit_row)
        preset = self.pd.material_preset[profile] if profile is not None else None
        values = self.pd.HMI_ValueStruct
        if key == 'TEMP':
            self.checkkey = self.ETemp
            values.E_Temp = preset.hotend_temp if preset else self.pd.state.status[self.pd.capabilities.active_hotend.name]['target']
            value = values.E_Temp
        elif key == 'BED':
            self.checkkey = self.BedTemp
            values.Bed_Temp = preset.bed_temp if preset else self.pd.state.status['heater_bed']['target']
            value = values.Bed_Temp
        else:
            self.checkkey = self.FanSpeed
            values.Fan_speed = self.pd.thermalManager['fan_speed'][0]
            value = values.Fan_speed
        if key in ('TEMP','BED'):
            self._draw_thermal_target(value,self.MBASE(self._thermal_edit_row),self.lcd.Select_Color)
        else:
            self._draw_menu_value(str(value), self.MBASE(self._thermal_edit_row),
                                  self.lcd.Select_Color, self.MENU_NARROW_CELLS)

    def _draw_menu_value(self, text, y, bg, cells=7):
        """Draw exactly one background-filled menu field at the shared right edge.

        A fixed-length opaque 0x11 text packet overwrites old digits when
        numbers shrink; rendering does not depend on the previous value or
        on the installed font artwork (both variants use 8x16 cells).
        """
        text = str(text)
        if len(text) > cells:
            text = '#' * cells
        x = self.MENU_VALUE_RIGHT - cells * self.MENU_CHR_W
        self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                           bg, x, y, text.rjust(cells))

    def _draw_thermal_target(self, value, y, bg):
        text = compact(value)
        if len(text) > self.MENU_WIDE_CELLS:
            text = str(int(value))
        self._draw_menu_value(text, y, bg, self.MENU_WIDE_CELLS)

    def _draw_axis_value(self, index, scaled, y, bg):
        value = scaled / self.MINUNITMULT
        text = (fit_decimal(value, self.MENU_WIDE_CELLS) if index == 2
                else fixed(value, 1 if index == 3 else 2))
        if len(text) > self.MENU_WIDE_CELLS:
            text = fixed(value, 1)
        self._draw_menu_value(text, y, bg, self.MENU_WIDE_CELLS)

    def _draw_offset_value(self, scaled, y, bg):
        text = fit_decimal(scaled / 100, self.MENU_WIDE_CELLS)
        self._draw_menu_value(text, y, bg, self.MENU_WIDE_CELLS)

    def MBASE(self, L):
        return 49 + self.MLINE * L

    def Draw_Popup_Bkgd_105(self):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Window, 14, 105, 258, 374)

    def Draw_More_Icon(self, line):
        show_theme_icon(self.lcd, self.ICON, self.ICON_More, 226, self.MBASE(line) - 3)

    def Draw_Menu_Cursor(self, line):
        self.lcd.draw_rectangle(1, self.lcd.Rectangle_Color, 4, self.MBASE(line) - 13, 7, self.MBASE(line + 1) - 25)

    def Draw_Menu_Icon(self, line, icon):
        show_theme_icon(self.lcd, self.ICON, icon, 26, self.MBASE(line) - 3)

    def Draw_Menu_Line(self, line, icon=False, label=False):
        if (label):
            self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black, self.LBLX, self.MBASE(line) - 1, label)
        if (icon):
            self.Draw_Menu_Icon(line, icon)
        self.lcd.draw_line(self.lcd.Line_Color, 16, self.MBASE(line) + 33, 256, self.MBASE(line) + 34)

    def Draw_Back_First(self, is_sel=True):
        self._draw_header_back(is_sel)

    def _draw_menu_text(self, text, x, y):
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, x, y, text)

    def draw_move_en(self, line):
        self._draw_menu_text('Move', self.LBLX, line)

    def draw_max_en(self, line):
        self._draw_menu_text('Max', self.LBLX, line)

    def draw_max_accel_en(self, line):
        self._draw_menu_text('Max Acceleration', self.LBLX, line)

    def draw_speed_en(self, inset, line):
        self._draw_menu_text('Speed', self.LBLX + inset, line)

    def draw_jerk_en(self, line):
        self._draw_menu_text('Jerk', self.LBLX + 27, line)

    def draw_steps_per_mm(self, line):
        self._draw_menu_text('Steps-per-mm', self.LBLX, line)

    def Clear_Title_Bar(self):
        self._info_render_scroll = None
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Blue, 0, 0, self.lcd.DWIN_WIDTH - 1, 30)
        self._invalidate_header()
        self._draw_header_clock()

    def Clear_Menu_Area(self):
        self._list_render = None
        self._display_drawn_message = None
        self._file_drawn_message = None
        self._home_mmu_layout = None
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH - 1, self.STATUS_Y)

    def Clear_Main_Window(self):
        self._spool_stop_scan_animation()
        self._info_render_scroll = None
        component = getattr(self, '_nfc_uri_share', None)
        if component is not None:
            component.invalidate()
        self._screws_result_cache = None
        self.Clear_Title_Bar()
        self.Clear_Menu_Area()

    def Clear_Popup_Area(self):
        self._spool_stop_scan_animation()
        component = getattr(self, '_nfc_uri_share', None)
        if component is not None:
            component.stop_animation()
        self._info_render_scroll = None
        # Popup overwrites previously cached screw graphics; power-cancel
        # must repaint all four corners when returning to that screen.
        self._screws_result_cache = None
        self._sync_fan_animation(False)
        self._list_render = None
        self._status_layout = None
        self.Clear_Title_Bar()
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH - 1, self.lcd.DWIN_HEIGHT - 1)

    def Erase_Menu_Cursor(self, line):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, self.MBASE(line) - 18, 14, self.MBASE(line + 1) - 20)

    def Erase_Menu_Text(self, line):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, self.LBLX, self.MBASE(line) - 14, 271, self.MBASE(line) + 28)

    def Move_Highlight(self, ffrom, newline):
        self.Erase_Menu_Cursor(newline - ffrom)
        self.Draw_Menu_Cursor(newline)

    def Add_Menu_Line(self):
        self.Move_Highlight(1, self.MROWS)
        self.lcd.draw_line(self.lcd.Line_Color, 16, self.MBASE(self.MROWS + 1) - 20, 256, self.MBASE(self.MROWS + 1) - 19)

    def Scroll_Menu(self, dir):
        self.lcd.move_area(1, dir, self.MLINE, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH, 349)
        if dir == self.DWIN_SCROLL_DOWN:
            self.Move_Highlight(-1, 0)
        elif dir == self.DWIN_SCROLL_UP:
            self.Add_Menu_Line()
