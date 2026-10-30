"""Existing display methods grouped by responsibility."""
from petrel.ui.theme import show_icon as show_theme_icon
from petrel.artwork.resources import ICON_RFID_HOME_NORMAL, ICON_RFID_HOME_SELECTED
import copy


class HomeViewMixin:
    def _home_entries(self):
        entries = [('PRINT', 'Print', self.ICON_Print_0, self.ICON_Print_1),
                   ('PREPARE', 'Prepare', self.ICON_Prepare_0, self.ICON_Prepare_1),
                   ('CONTROL', 'Control', self.ICON_Control_0, self.ICON_Control_1)]
        if len(self._leveling_menu_entries()) > 1:
            entries.append(('LEVEL', 'Leveling', self.ICON_Leveling_0, self.ICON_Leveling_1))
        entries.append(('MMU', 'MMU', self.ICON_MMU_0, self.ICON_MMU_1))
        entries.append(('DISPLAY', 'Device', self.ICON_Display_0, self.ICON_Display_1))
        entries.append(('MAINTENANCE', 'Maintenance', self.ICON_Maintenance_0, self.ICON_Maintenance_1))
        entries.append(('RFID', 'NFC', ICON_RFID_HOME_NORMAL, ICON_RFID_HOME_SELECTED))
        # Home navigation contract: append new features above Info; Info is always last.
        entries.append(('INFO', 'Info', self.ICON_Info_0, self.ICON_Info_1))
        return tuple(entries)

    def _draw_home_page(self, previous=None):
        entries = self._home_entries()
        self.select_page.set(min(self.select_page.now, len(entries)-1))
        page = self.select_page.now // 4
        partial = previous is not None and previous // 4 == page
        if not partial:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 126, 271, self.STATUS_Y-1)
        indices = (previous, self.select_page.now) if partial else range(
            page*4, min(len(entries), page*4+4))
        for index in indices:
            key, label, normal, selected = entries[index]
            slot = index % 4
            x, y = (17 if slot % 2 == 0 else 145), (130 if slot < 2 else 246)
            active = index == self.select_page.now
            if partial:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, x, y, x+109, y+99)
            show_theme_icon(self.lcd, self.ICON, selected if active else normal, x, y)
            # Demo selection is built into the rounded selected tile asset.
            self._draw_menu_text(label, x+(109-len(label)*8)//2, y+71)
        pages = (len(entries)+3)//4
        if pages > 1 and not partial:
            spacing = min(18, 256 // pages)
            first_x = 136 - (pages - 1) * spacing // 2
            for number in range(pages):
                draw = self.lcd.fill_circle if number == page else self.lcd.draw_circle
                draw(self.lcd.Color_White if number == page else 0x8410,
                     first_x + number * spacing, 354, 4)

    def HMI_MainMenu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        entries = self._home_entries()
        self.select_page.set(min(self.select_page.now, len(entries)-1))
        previous = self.select_page.now
        if event == self.ENCODER_DIFF_CW:
            self.select_page.inc(len(entries))
        elif event == self.ENCODER_DIFF_CCW:
            self.select_page.dec()
        elif event == self.ENCODER_DIFF_ENTER:
            key = entries[self.select_page.now][0]
            if key == 'PRINT':
                self.checkkey = self.SelectFile
                self._file_directory = ''
                self._file_paths = ()
                self.select_file.reset()
                self._refresh_file_snapshot()
                self.Draw_Print_File_Menu()
            elif key == 'PREPARE':
                self.checkkey = self.Prepare
                self.select_prepare.reset()
                self.index_prepare = self.MROWS
                self.Draw_Prepare_Menu()
            elif key == 'CONTROL':
                self.checkkey = self.Control
                self.select_control.reset()
                self.index_control = self.MROWS
                self.Draw_Control_Menu()
            elif key == 'LEVEL':
                self.checkkey = self.Leveling
                self.HMI_Leveling()
            elif key == 'MMU':
                self.Enter_MMU_Menu()
            elif key == 'DISPLAY':
                self.checkkey = self.DisplayMenu
                self.Draw_Display_Menu()
            elif key == 'MAINTENANCE':
                # Discovery has already run at Klipper READY; this is only
                # an entry safety check, never a capability API request.
                from petrel.features.maintenance.discovery.session import idle
                if idle(self.pd.state):
                    self.Enter_Maintenance_Menu()
            elif key == 'RFID':
                self._rfid_cancel_assignment()
                self._rfid_mode = 'info'
                self._rfid_selection = 0
                self.checkkey = self.RFIDMenu
                self.Draw_RFID_Menu()
            elif key == 'INFO':
                self._info_origin = self.MainMenu
                self.checkkey = self.Info
                self.Draw_Info_Menu()
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW) and previous != self.select_page.now:
            self._draw_home_page(previous)
        self.lcd.update()

    def HMI_Prepare(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self._menu_navigation('prepare', self.select_prepare, 'index_prepare', self.Draw_Prepare_Menu):
            return
        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.select_prepare.now == 0):  # Back
                self.select_page.set(1)
                self.Goto_MainMenu()

            elif self.select_prepare.now == self.PREPARE_CASE_MOVE:  # Axis move
                self.checkkey = self.AxisMove
                self.select_axis.reset()
                self.Draw_Move_Menu()
            elif self.select_prepare.now == self.PREPARE_CASE_DISA:  # Disable steppers
                self._action("Disable steppers", lambda: self.pd.sendGCode("M84"), silent=True)
            elif self.select_prepare.now == self.PREPARE_CASE_HOME:  # Homing
                self.checkkey = self.Last_Prepare
                self.index_prepare = self.MROWS
                self.pd.current_position.homing()
                self.pd.HMI_flag.home_flag = True
                self.Popup_Window_Home()
                self._action("Home", lambda: self.pd.sendGCodeObserved("G28"),
                             self.pd.ishomed, confirmation_timeout=600, silent=True,
                             on_accept=self._restore_action_screen)
            elif self.select_prepare.now == self.PREPARE_CASE_ZOFF:  # Z-offset
                self._open_zoffset(-4, self.PREPARE_CASE_ZOFF + self.MROWS - self.index_prepare)

            elif self.select_prepare.now > 0 and self._menus['prepare'][self.select_prepare.now - 1][0].startswith('PRESET:'):
                profile = int(self._menus['prepare'][self.select_prepare.now - 1][0].split(':', 1)[1])
                name = self.pd.material_preset[profile].name
                self._action('Preheat ' + name, lambda profile=profile: self.pd.preheat_preset(profile, idle_only=True), silent=True)

            elif self.select_prepare.now == self.PREPARE_CASE_COOL:  # Cool
                self._action('Cooldown', lambda: self.pd.cooldown(idle_only=True), silent=True)

        self.lcd.update()

    def HMI_Control(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self._menu_navigation('control', self.select_control, 'index_control', self.Draw_Control_Menu):
            return
        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.select_control.now == 0):  # Back
                self.select_page.set(2)
                self.Goto_MainMenu()
            if (self.select_control.now == self.CONTROL_CASE_TEMP):  # Temperature
                self.checkkey = self.TemperatureID
                self.pd.HMI_ValueStruct.show_mode = -1
                self.select_temp.reset()
                self.Draw_Temperature_Menu()
            if (self.select_control.now == self.CONTROL_CASE_MOVE):  # Motion
                self.checkkey = self.Motion
                self.select_motion.reset()
                self.Draw_Motion_Menu()
            if self.select_control.now == self.CONTROL_CASE_RECOVERY:
                self._action('Restore jog state', self.pd.restore_jog_state, silent=True)
            if self.select_control.now == self.CONTROL_CASE_LIGHT:
                self.checkkey = self.CaseLight
                self.select_light.reset()
                self._sync_case_light_tracking()
                self._poll_case_light_state(redraw=False)
                self.Draw_Case_Light_Menu()
            if (self.select_control.now == self.CONTROL_CASE_INFO):  # Info
                self._info_origin = self.Control
                self.checkkey = self.Info
                self.Draw_Info_Menu()

        self.lcd.update()

    def Draw_Prepare_Menu(self):
        self._draw_capability_menu('prepare', self.select_prepare, self.index_prepare)

    def Draw_Control_Menu(self):
        self._draw_capability_menu('control', self.select_control, getattr(self, 'index_control', self.MROWS))

    def Goto_MainMenu(self):
        self.checkkey = self.MainMenu
        self.Clear_Main_Window()

        if self.pd.mmu is None:
            show_theme_icon(self.lcd, self.ICON, self.ICON_LOGO, 71, 48)
        else:
            self.Draw_MMU_Status()
        self._drawn_mmu_state = copy.deepcopy(self.pd.mmu)

        self._draw_home_page()

    def ICON_Print(self):
        if self.select_page.now == 0:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Print_1, 17, 130)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 17, 130, 126, 229)
            self._draw_menu_text('Print', 57, 201)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Print_0, 17, 130)
            self._draw_menu_text('Print', 57, 201)

    def ICON_Prepare(self):
        if self.select_page.now == 1:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Prepare_1, 145, 130)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 130, 254, 229)
            self._draw_menu_text('Prepare', 175, 201)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Prepare_0, 145, 130)
            self._draw_menu_text('Prepare', 175, 201)

    def ICON_Control(self):
        if self.select_page.now == 2:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Control_1, 17, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 17, 246, 126, 345)
            self._draw_menu_text('Control', 48, 318)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Control_0, 17, 246)
            self._draw_menu_text('Control', 48, 318)

    def ICON_Leveling(self, show):
        if show:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Leveling_1, 145, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 246, 254, 345)
            self._draw_menu_text('Leveling', 182, 318)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Leveling_0, 145, 246)
            self._draw_menu_text('Leveling', 182, 318)

    def ICON_StartInfo(self, show):
        if show:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Info_1, 145, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 246, 254, 345)
            self._draw_menu_text('Info', 186, 318)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Info_0, 145, 246)
            self._draw_menu_text('Info', 186, 318)

    def Item_Prepare_Move(self, row):
        self.draw_move_en(self.MBASE(row))  # "Move >"
        self.Draw_Menu_Line(row, self.ICON_Axis)
        self.Draw_More_Icon(row)

    def Item_Prepare_Disable(self, row):
        self._draw_menu_text('Disable steppers', self.LBLX, self.MBASE(row))  # Disable Stepper"
        self.Draw_Menu_Line(row, self.ICON_CloseMotor)

    def Item_Prepare_Home(self, row):
        self._draw_menu_text('Auto home', self.LBLX, self.MBASE(row))  # Auto Home"
        self.Draw_Menu_Line(row, self.ICON_Homing)

    def Item_Prepare_Offset(self, row):
        if self.pd.HAS_BED_PROBE:
            self._draw_menu_text('Z offset', self.LBLX, self.MBASE(row))  # "Z-Offset"
            self._draw_offset_value(self.pd.BABY_Z_VAR * 100,self.MBASE(row),self.lcd.Color_Bg_Black)
        else:
            self._draw_menu_text('Set home', self.LBLX, self.MBASE(row))  # "..."
        self.Draw_Menu_Line(row, self.ICON_SetHome)

    def Item_Prepare_PLA(self, row):
        self._draw_menu_text('Preheat PLA', self.LBLX, self.MBASE(row))
        self.Draw_Menu_Line(row, self.ICON_PLAPreheat)

    def Item_Prepare_Cool(self, row):
        self._draw_menu_text('Cooldown', self.LBLX, self.MBASE(row))  # "Cooldown"
        self.Draw_Menu_Line(row, self.ICON_Cool)
