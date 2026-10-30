"""Existing display methods grouped by responsibility."""
from petrel.artwork.resources import ICON_BRIGHTNESS, ICON_BUZZER, ICON_CLICK_TONE, ICON_DIM_BRIGHTNESS, ICON_ENCODER_TONE, ICON_IDLE_DIM, ICON_VOLUME
from petrel.artwork.resources import ICON_NFC
import petrel.features.display_settings.settings as display_settings
import time
from petrel.hardware.dwin.driver import T5UIC1ProtocolError


class DisplaySettingsViewMixin:
    def _display_activity(self):
        panel = getattr(getattr(self,'pd',None),'maintenance_panel',None)
        if panel is not None and panel.pending:
            self._display_last_activity = time.monotonic()
            return False
        self._display_last_activity = time.monotonic()
        if getattr(self, '_display_dimmed', False):
            self._display_dimmed = False
            self.lcd.set_backlight(display_settings.raw_brightness(self._display_values[0]))
            return True  # First interaction wakes without activating a hidden action.
        return False

    def _display_idle_tick(self):
        panel = getattr(getattr(self,'pd',None),'maintenance_panel',None)
        if panel is not None and panel.pending:
            return
        values = getattr(self, '_display_values', None)
        if (values and values[1] and not getattr(self, '_display_dimmed', False)
                and time.monotonic() - self._display_last_activity >= values[1] * 60
                and not getattr(self, '_display_edit', False)):
            self.lcd.set_backlight(display_settings.raw_brightness(min(values[0], values[2])))
            self._display_dimmed = True

    def Draw_Display_Menu(self):
        selection = getattr(self, '_display_selection', 0)
        values = getattr(self, '_display_values', [100, 0, 10])
        entries = [('Back', self.ICON_Back, None, None)]
        for row, label, icon, text in (
                (1, 'Brightness', ICON_BRIGHTNESS, str(values[0]) + '%'),
                (2, 'Idle dim', ICON_IDLE_DIM, str(values[1]) + ' min' if values[1] else 'Off'),
                (3, 'Dim brightness', ICON_DIM_BRIGHTNESS, str(values[2]) + '%')):
            editing = getattr(self, '_display_edit', False) and selection == row
            painter = lambda row, text=text, editing=editing: self._draw_menu_value(
                text, self.MBASE(row) - 1,
                self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black,
                self.MENU_WIDE_CELLS)
            entries.append((label, icon, (text, editing), painter))
        for row, (label, text, editable) in enumerate(self._buzzer_rows(), 4):
            editing = getattr(self, '_display_edit', False) and selection == row
            # Use the *same* fixed-width, opaque right-edge value renderer
            # as Brightness/Idle dim above. The old variable-width 0x11
            # text mode left artifacts and misaligned Enabled/Disabled.
            painter = lambda row, text=text, editing=editing: self._draw_menu_value(
                text, self.MBASE(row) - 1,
                self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black, 10)
            entries.append((label, {'Buzzer': ICON_BUZZER,'Volume': ICON_VOLUME,'Click tone': ICON_CLICK_TONE,'Encoder tone': ICON_ENCODER_TONE}[label], (text, editing), painter))
        entries.append(('Event sounds', ICON_BUZZER, None, None))
        entries.append(('NFC settings', ICON_NFC, None, None))
        self._display_selection = min(selection, len(entries) - 1)
        save_message = getattr(self, '_display_save_message', '')
        title = ('Device - saving...' if save_message == 'Saving...' else
                 'Device - not saved' if save_message else 'Device settings')
        self._draw_list_menu(title, entries, self._display_selection)

    def HMI_Display_Menu(self):
        event = self.get_encoder_state()
        if (getattr(self, '_display_save_future', None) is not None
                or getattr(self, '_buzzer_save_future', None) is not None):
            # Do not accept another editor value while Flash ACK is pending.
            return
        if self._buzzer_display_input(event):
            return
        selection = getattr(self, '_display_selection', 0)
        editing = getattr(self, '_display_edit', False)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            delta = getattr(self,"_rotation_steps",1)*(1 if event == self.ENCODER_DIFF_CW else -1)
            if editing:
                index = selection - 1
                self._display_values[index] = max(0, min(60 if index == 1 else 100,
                                                       self._display_values[index] + delta))
                if index == 0:
                    self.lcd.set_backlight(display_settings.raw_brightness(self._display_values[0]))
            else:
                self._display_selection = max(0, min(5 + len(self._buzzer_rows()), selection + delta))
            self._display_save_message = ''
        elif event == self.ENCODER_DIFF_ENTER:
            if selection == 0:
                self.select_page.set(next(i for i, entry in enumerate(self._home_entries())
                                          if entry[0] == 'DISPLAY'))
                self.Goto_MainMenu()
                self.lcd.update()
                return
            if selection == 4 + len(self._buzzer_rows()):
                self._event_sound_selection = 0
                self._event_sound_message = ''
                self.checkkey = self.EventSoundsMenu
                self.Draw_Event_Sounds_Menu()
                self.lcd.update()
                return
            if selection == 5 + len(self._buzzer_rows()):
                self._nfc_selection = 0
                self._nfc_scroll_start = 0
                self._nfc_choice_field = None
                self._nfc_choice_options = ()
                self._nfc_port_choices = None
                self._nfc_port_future = None
                self._nfc_port_error = False
                self._nfc_save_error = False
                self.checkkey = self.NFCSettingsMenu
                self.Draw_NFC_Settings_Menu()
                self.lcd.update()
                return
            if editing:
                try:
                    values = tuple(self._display_values)
                    if values != self._display_saved:
                        if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                            record = display_settings.encode(*values)
                            self._display_save_target = values
                            self._panel_flash_lcd = self.lcd
                            self._display_save_future = self.lcd.begin_flash_write_verified(
                                self.lcd.DISPLAY_SETTINGS_ADDRESS, record)
                            self._display_save_message = 'Saving...'
                        else:
                            self.lcd.save_display_settings(*values)
                            self._display_saved = values
                            self._display_edit = False
                            self._display_save_message = ''
                    else:
                        self._display_edit = False
                        self._display_save_message = ''
                except (OSError, TimeoutError, T5UIC1ProtocolError):
                    self._display_save_message = 'Not saved. Press to retry'
            else:
                self._display_edit = True
        else:
            return
        self.Draw_Display_Menu()
        self.lcd.update()
