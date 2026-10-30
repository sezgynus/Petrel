"""Existing display methods grouped by responsibility."""
from petrel.ui.theme import show_icon as show_theme_icon
from petrel.artwork.resources import ICON_STOP_BUTTON_SELECTED
from concurrent.futures import Future


class TemperatureViewMixin:
    def HMI_Temperature(self):
        event = self.get_encoder_state()
        if self._menu_navigation('temperature', self.select_temp, 'index_temp', self.Draw_Temperature_Menu):
            return
        if event != self.ENCODER_DIFF_ENTER:
            return
        if self.select_temp.now == 0:
            self.checkkey = self.Control
            self.select_control.set(self.CONTROL_CASE_TEMP)
            self.Draw_Control_Menu()
        else:
            key = self._menus['temperature'][self.select_temp.now - 1][0]
            if key.startswith('PRESET:'):
                profile = int(key.split(':', 1)[1])
                self._active_preset = profile
                self.checkkey = self.PLAPreheat
                self.select_PLA.reset()
                self.pd.HMI_ValueStruct.show_mode = -2
                self._draw_capability_menu('preheat', self.select_PLA, profile=profile)
            else:
                self.pd.HMI_ValueStruct.show_mode = -1
                self._open_thermal_editor(key, self.select_temp.now)
        self.lcd.update()

    def _preset_hmi(self, profile=None):
        profile = getattr(self, '_active_preset', 0) if profile is None else profile
        if not 0 <= profile < len(self.pd.material_preset):
            self.checkkey = self.TemperatureID
            self.select_temp.reset()
            self.Draw_Temperature_Menu()
            self.lcd.update()
            return
        selection = self.select_PLA
        draw = lambda: self._draw_capability_menu('preheat', selection, profile=profile)
        if self._menu_navigation('preheat', selection, 'index_preset', draw):
            return
        if self.get_encoder_state() != self.ENCODER_DIFF_ENTER:
            return
        if selection.now == 0:
            self.checkkey = self.TemperatureID
            self.pd.HMI_ValueStruct.show_mode = -1
            self.Draw_Temperature_Menu()
        else:
            key = self._menus['preheat'][selection.now - 1][0]
            if key == 'CANCEL':
                self.pd.discard_preset_edits(profile)
                draw()
            elif key == 'SAVE':
                future = self.pd.save_settings()
                if isinstance(future, Future):
                    self._action('Save presets', lambda: future, silent=True,
                                 on_accept=lambda: draw() if self.checkkey in (self.PLAPreheat, self.ABSPreheat)
                                 and getattr(self, '_active_preset', 0) == profile else None)
                else:
                    self.HMI_AudioFeedback(future)
            else:
                self._open_thermal_editor(key, selection.now, profile)
        self.lcd.update()

    def HMI_PLAPreheatSetting(self):
        self._preset_hmi()

    def HMI_ABSPreheatSetting(self):
        self._preset_hmi()

    def HMI_FanSpeed(self):
        event = self.get_encoder_state()
        mode = self.pd.HMI_ValueStruct.show_mode
        if mode == -1:
            row = self.TEMP_CASE_FAN
        else:
            row = self.TUNE_CASE_FAN + self.MROWS - self.index_tune
        row = getattr(self, '_thermal_edit_row', row)
        if event == self.ENCODER_DIFF_ENTER:
            value = self.pd.HMI_ValueStruct.Fan_speed
            if mode != -2:
                self._action("Fan speed", lambda: self.pd.setFanSpeed(value, idle_only=mode == -1), silent=True)
                self.checkkey = self.TemperatureID if mode == -1 else self.Tune
                self.Draw_Temperature_Menu() if mode == -1 else self.Draw_Tune_Menu()
        elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            value = self.pd.HMI_ValueStruct.Fan_speed + (self._encoder_move_value if event == self.ENCODER_DIFF_CW else -self._encoder_move_value)
            self.pd.HMI_ValueStruct.Fan_speed = max(0, min(100, value))
            self._draw_menu_value(str(self.pd.HMI_ValueStruct.Fan_speed),
                                  self.MBASE(row), self.lcd.Select_Color,
                                  self.MENU_NARROW_CELLS)
        self.lcd.update()

    def HMI_ETemp(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self.pd.HMI_ValueStruct.show_mode == -1:
            temp_line = self.TEMP_CASE_TEMP
        elif self.pd.HMI_ValueStruct.show_mode == -2:
            temp_line = self.PREHEAT_CASE_TEMP
        else:
            temp_line = self.TUNE_CASE_TEMP + self.MROWS - self.index_tune

        temp_line = getattr(self, '_thermal_edit_row', temp_line)
        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.pd.HMI_ValueStruct.show_mode == -1):  # temperature
                self.checkkey = self.TemperatureID
                self._draw_thermal_target(self.pd.HMI_ValueStruct.E_Temp,self.MBASE(temp_line),self.lcd.Color_Bg_Black)
            elif (self.pd.HMI_ValueStruct.show_mode == -2):
                self.checkkey = self.PLAPreheat
                profile = getattr(self, '_active_preset', 0)
                self.pd.material_preset[profile].hotend_temp = self.pd.HMI_ValueStruct.E_Temp
                self._draw_thermal_target(self.pd.material_preset[profile].hotend_temp,self.MBASE(temp_line),self.lcd.Color_Bg_Black)
                return
            else:  # tune
                self.checkkey = self.Tune
                self._draw_thermal_target(self.pd.HMI_ValueStruct.E_Temp,self.MBASE(temp_line),self.lcd.Color_Bg_Black)
            self._action("Hotend target", lambda: self.pd.setExtTemp(self.pd.HMI_ValueStruct.E_Temp, idle_only=self.pd.HMI_ValueStruct.show_mode == -1), silent=True)
            return

        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.E_Temp += self._encoder_move_value

        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.E_Temp -= self._encoder_move_value

        # E_Temp limit
        if self.pd.HMI_ValueStruct.E_Temp > self.pd.MAX_E_TEMP:
            self.pd.HMI_ValueStruct.E_Temp = self.pd.MAX_E_TEMP
        if self.pd.HMI_ValueStruct.E_Temp < self.pd.MIN_E_TEMP:
            self.pd.HMI_ValueStruct.E_Temp = self.pd.MIN_E_TEMP
        heater = self.pd.capabilities.active_hotend
        if heater and 0 < self.pd.HMI_ValueStruct.E_Temp < heater.minimum:
            self.pd.HMI_ValueStruct.E_Temp = heater.minimum if encoder_diffState == self.ENCODER_DIFF_CW else 0
        # E_Temp value
        self._draw_thermal_target(self.pd.HMI_ValueStruct.E_Temp,self.MBASE(temp_line),self.lcd.Select_Color)

    def HMI_BedTemp(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self.pd.HMI_ValueStruct.show_mode == -1:
            bed_line = self.TEMP_CASE_BED
        elif self.pd.HMI_ValueStruct.show_mode == -2:
            bed_line = self.PREHEAT_CASE_BED
        else:
            bed_line = self.TUNE_CASE_BED + self.MROWS - self.index_tune

        bed_line = getattr(self, '_thermal_edit_row', bed_line)
        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.pd.HMI_ValueStruct.show_mode == -1):  # temperature
                self.checkkey = self.TemperatureID
                self._draw_thermal_target(self.pd.HMI_ValueStruct.Bed_Temp,self.MBASE(bed_line),self.lcd.Color_Bg_Black)
            elif (self.pd.HMI_ValueStruct.show_mode == -2):
                self.checkkey = self.PLAPreheat
                profile = getattr(self, '_active_preset', 0)
                self.pd.material_preset[profile].bed_temp = self.pd.HMI_ValueStruct.Bed_Temp
                self._draw_thermal_target(self.pd.material_preset[profile].bed_temp,self.MBASE(bed_line),self.lcd.Color_Bg_Black)
                return
            else:  # tune
                self.checkkey = self.Tune
                self._draw_thermal_target(self.pd.HMI_ValueStruct.Bed_Temp,self.MBASE(bed_line),self.lcd.Color_Bg_Black)
            self._action("Bed target", lambda: self.pd.setBedTemp(self.pd.HMI_ValueStruct.Bed_Temp, idle_only=self.pd.HMI_ValueStruct.show_mode == -1), silent=True)
            return

        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Bed_Temp += self._encoder_move_value

        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Bed_Temp -= self._encoder_move_value

        # Bed_Temp limit
        if self.pd.HMI_ValueStruct.Bed_Temp > self.pd.BED_MAX_TARGET:
            self.pd.HMI_ValueStruct.Bed_Temp = self.pd.BED_MAX_TARGET
        if self.pd.HMI_ValueStruct.Bed_Temp < self.pd.MIN_BED_TEMP:
            self.pd.HMI_ValueStruct.Bed_Temp = self.pd.MIN_BED_TEMP
        heater = self.pd.capabilities.bed
        if heater and 0 < self.pd.HMI_ValueStruct.Bed_Temp < heater.minimum:
            self.pd.HMI_ValueStruct.Bed_Temp = heater.minimum if encoder_diffState == self.ENCODER_DIFF_CW else 0
        # Bed_Temp value
        self._draw_thermal_target(self.pd.HMI_ValueStruct.Bed_Temp,self.MBASE(bed_line),self.lcd.Select_Color)

    def Draw_Temperature_Menu(self):
        self._draw_capability_menu('temperature', self.select_temp, self.index_temp)

    def Popup_Window_ETempTooLow(self):
        self.Clear_Main_Window()
        self.Draw_Popup_Bkgd_60()
        show_theme_icon(self.lcd, self.ICON, self.ICON_TempTooLow, 102, 105)
        self.lcd.draw_text(
            False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color,
            self.lcd.Color_Bg_Window, 20, 235,
            "Nozzle is too cold"
        )
        # Reuse a text-free managed backing; keep the label localizable.
        show_theme_icon(self.lcd, self.ICON, ICON_STOP_BUTTON_SELECTED, 84, 280)
        label = 'Confirm'
        self.lcd.draw_text(
            False, False, self.lcd.font8x16, 0x10C4, 0x063B,
            (272 - len(label) * 8) // 2, 290, label)
