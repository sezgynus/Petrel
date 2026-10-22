"""Display menu NFC reader configuration and standard choice submenus."""
from dataclasses import replace
import logging
from lcd_resources import ICON_NFC
from nfc_settings import (BAUD_RATES, NFCSettings, PROFILES,
                          available_ports, installed_enabled, load, save)


NFC_FIELDS = ((2, 'model', 'RFID module'),
              (3, 'interface', 'Interface'),
              (4, 'port', 'Port / device'),
              (5, 'speed', 'Link speed'))


class NFCSettingsViewMixin:
    def _nfc_enabled(self):
        return installed_enabled()

    def _nfc_config(self):
        value = getattr(self, '_nfc_values', None)
        if not isinstance(value, NFCSettings):
            value = load()
            self._nfc_values = self._nfc_saved = value
            configured = bool(value.port)
            self._nfc_confirmed = {'model': configured, 'interface': configured, 'port': configured}
        return value

    def _nfc_options(self, field):
        value = self._nfc_config()
        if field == 'model':
            return tuple(PROFILES)
        if field == 'interface':
            return PROFILES[value.model]['interfaces']
        if field == 'port':
            key = (value.model, value.interface)
            cached = getattr(self, '_nfc_port_choices', None)
            # Never discover NFC hardware while rendering (or from any
            # menu method). Backend/Moonraker workers supply a cached result.
            return cached[1] if cached is not None and cached[0] == key else ()
        if field == 'speed' and value.interface == 'UART':
            return BAUD_RATES
        return ()

    def _nfc_field_enabled(self, field):
        confirmed = getattr(self, '_nfc_confirmed', {})
        if field == 'model':
            return True
        if field == 'interface':
            return confirmed.get('model', False)
        if field == 'port':
            # A confirmed UART interface may be opened to discover devices
            # even before a result exists, or after a failed/empty result.
            return (confirmed.get('interface', False) and
                    (self._nfc_config().interface == 'UART'
                     or bool(self._nfc_options('port'))))
        if field == 'speed':
            return (confirmed.get('port', False)
                    and self._nfc_config().interface == 'UART')
        return False

    def _nfc_focusable(self):
        fields = {2: 'model', 3: 'interface', 4: 'port', 5: 'speed'}
        result = [0]
        result.extend(row for row, field in fields.items() if self._nfc_field_enabled(field))
        value = self._nfc_config()
        confirmed = getattr(self, '_nfc_confirmed', {})
        cached = getattr(self, '_nfc_port_choices', None)
        port_available = (
            bool(value.port) and
            (cached is None or cached[0] != (value.model, value.interface)
             or value.port in cached[1])
        ) if value.interface == 'UART' else value.port in self._nfc_options('port')
        if (all(confirmed.get(field, False)
                for field in ('model', 'interface', 'port')) and port_available):
            result.append(6)
            result.append(7)
        return result

    def _nfc_value_text(self, field):
        value = self._nfc_config()
        confirmed = getattr(self, '_nfc_confirmed', {})
        if field == 'speed':
            if value.interface != 'UART':
                return 'Not applicable'
            return str(value.speed) if confirmed.get('port', False) else 'Select'
        if not confirmed.get(field, False):
            if (field == 'port' and confirmed.get('interface', False)
                    and value.interface != 'UART' and not self._nfc_options('port')):
                return 'Unavailable'
            return 'Select'
        current = str(getattr(value, field))
        if field == 'port':
            # Full device path remains available in its selection list.
            name = current.rsplit('/', 1)[-1]
            return name if len(name) <= 9 else '...' + name[-6:]
        return current

    def _nfc_value_painter(self, label, value, active, cells=10, color=None):
        # Match the shared right-aligned Display menu value column. Inactive
        # labels/values are grey; long paths never overlap their left labels.
        def paint(row):
            y = self.MBASE(row) - 1
            if active:
                if color is None:
                    self._draw_menu_value(value, y, self.lcd.Color_Bg_Black, cells)
                else:
                    # Same opaque right-aligned value field as other menu
                    # options; only the connection result is state-colored.
                    self.lcd.draw_text(
                        False, True, self.lcd.font8x16, color,
                        self.lcd.Color_Bg_Black,
                        self.MENU_VALUE_RIGHT - cells * self.MENU_CHR_W,
                        y, str(value).rjust(cells))
            else:
                text = str(value)[:cells].rjust(cells)
                self.lcd.draw_text(False, True, self.lcd.font8x16, 0x8410,
                                   self.lcd.Color_Bg_Black,
                                   self.MENU_VALUE_RIGHT - cells * self.MENU_CHR_W,
                                   y, text)
                self.lcd.draw_text(False, True, self.lcd.font8x16, 0x8410,
                                   self.lcd.Color_Bg_Black, self.LBLX, y, label)
        return paint

    def _nfc_status_painter(self, status, enabled):
        """Align read-only status with the shared menu label/value columns."""
        def paint(row):
            y = self.MBASE(row) - 1
            self._draw_menu_text('NFC feature', self.LBLX, y)
            # Full "Disabled in setup" overlaps the label at x=LBLX;
            # the feature origin is already clear from its read-only state.
            shown = 'Enabled' if enabled else 'Disabled'
            cells = 8
            self.lcd.draw_text(False, True, self.lcd.font8x16,
                               0x07E0 if enabled else 0x9CD3,
                               self.lcd.Color_Bg_Black,
                               self.MENU_VALUE_RIGHT - cells * self.MENU_CHR_W,
                               y, shown.rjust(cells))
        return paint

    def _nfc_schedule_port_discovery(self):
        value = self._nfc_config()
        confirmed = getattr(self, '_nfc_confirmed', {})
        if (not self._nfc_enabled() or not confirmed.get('interface', False)
                or value.interface == 'UART'
                or getattr(self, '_nfc_port_future', None) is not None):
            return
        key = (value.model, value.interface)
        if getattr(self, '_nfc_port_choices', None) is not None:
            if self._nfc_port_choices[0] == key:
                return
        self._nfc_port_future = self.pd.discover_nfc_devices(*key)

    def Draw_NFC_Settings_Menu(self):
        self._nfc_schedule_port_discovery()
        enabled = self._nfc_enabled()
        value = self._nfc_config()
        status = 'Enabled' if enabled else 'Disabled in setup'
        rows = [('Back', self.ICON_Back, None, None),
                # Empty label/icon: the standard list renderer skips action
                # artwork and separator; only the Info-style status is drawn.
                ('', None, status, self._nfc_status_painter(status, enabled))]
        for _, field, label in NFC_FIELDS:
            active = enabled and self._nfc_field_enabled(field)
            text = self._nfc_value_text(field)
            shown = 'N/A' if text == 'Not applicable' else (
                'No device' if text == 'Unavailable' else text)
            cells = 9 if field == 'port' else 10
            if len(shown) > cells:
                shown = shown[:cells - 3] + '...'
            rows.append((label, ICON_NFC if field == 'model' else self.ICON_Info,
                         (shown, active),
                         self._nfc_value_painter(label, shown, active, cells)))
        save_enabled = enabled and 6 in self._nfc_focusable()
        saved = value == getattr(self, '_nfc_saved', value)
        shown = 'Saved' if saved else 'Apply'
        running = getattr(self, '_nfc_test_future', None) is not None
        save_label = 'Busy' if running else shown
        rows.append(('Save', self.ICON_Info, (save_label, save_enabled),
                     self._nfc_value_painter('Save', save_label, save_enabled)))
        test_enabled = enabled and 7 in self._nfc_focusable()
        status = 'Run'
        if getattr(self, '_nfc_test_values', None) == value:
            status = 'Wait' if running else (
                getattr(self, '_nfc_test_state', None) or 'Run')
        result_color = (0x07E0 if status == 'OK' else
                        0xF800 if status == 'Fail' else None)
        # The full-width 9-character field overlaps "Test connection" on
        # 272px panels. Keep result values short and right-aligned.
        cells = 4
        rows.append(('Test connection', self.ICON_Info, (status, test_enabled),
                     self._nfc_value_painter('Test connection',
                                             status, test_enabled, cells,
                                             color=result_color)))
        # Encoder navigation follows every logical row, including unavailable
        # ones. Only enabled actions get a cursor and respond to Enter.
        self._nfc_selection = max(0, min(getattr(self, '_nfc_selection', 0),
                                          len(rows) - 1))
        active = self._nfc_enabled() and self._nfc_selection in self._nfc_focusable()
        focused = self._nfc_selection if (active or self._nfc_selection == 0) else None
        start = getattr(self, '_nfc_scroll_start', 0)
        start = max(0, min(start, self._nfc_selection),
                    self._nfc_selection - self.MROWS)
        self._nfc_scroll_start = start
        title = 'NFC Settings - not saved' if getattr(self, '_nfc_save_error', False) else 'NFC Settings'
        self._draw_list_menu(title, rows, focused, start=start)

    @staticmethod
    def _nfc_choice_label(value):
        text = str(value)
        # DWIN list content starts at x=60: at most 22 8px characters.
        return text if len(text) <= 22 else text[:7] + '...' + text[-12:]

    def _nfc_open_choice(self, field):
        if not self._nfc_enabled() or not self._nfc_field_enabled(field):
            return False
        value = self._nfc_config()
        serial = field == 'port' and value.interface == 'UART'
        if field == 'port':
            # Discovery has already completed asynchronously before entry.
            self._nfc_port_error = False
        options = () if serial else self._nfc_options(field)
        if not options and not serial:
            return False
        self._nfc_choice_field = field
        self._nfc_choice_options = options
        current = getattr(value, field)
        confirmed = getattr(self, '_nfc_confirmed', {})
        self._nfc_choice_selection = (
            options.index(current) + 1 if current in options and
            (field == 'speed' or confirmed.get(field, False)) else 0)
        self.checkkey = self.NFCChoiceMenu
        if serial:
            self._nfc_port_future = self.pd.discover_nfc_devices(value.model, value.interface)
        self.Draw_NFC_Choice_Menu()
        return True

    def _nfc_poll_port_choices(self):
        """Complete an on-demand UART discovery without blocking the UI."""
        future = getattr(self, '_nfc_port_future', None)
        if future is None or not future.done():
            return False
        self._nfc_port_future = None
        in_choice = (self.checkkey == self.NFCChoiceMenu
                     and getattr(self, '_nfc_choice_field', None) == 'port')
        if not in_choice and self.checkkey != self.NFCSettingsMenu:
            return False
        value = self._nfc_config()
        try:
            options = tuple(future.result())
        except Exception as exc:
            logging.warning('Moonraker NFC serial port discovery failed: %s', exc)
            options = ()
            self._nfc_port_error = True
        else:
            self._nfc_port_error = False
        self._nfc_port_choices = ((value.model, value.interface), options)
        if not in_choice:
            self.Draw_NFC_Settings_Menu()
            self.lcd.update()
            return True
        self._nfc_choice_options = options
        self._nfc_choice_selection = (
            options.index(value.port) + 1 if
            value.port in options and self._nfc_confirmed.get('port', False)
            else 0)
        self.Draw_NFC_Choice_Menu()
        self.lcd.update()
        return True

    def Draw_NFC_Choice_Menu(self):
        field = getattr(self, '_nfc_choice_field', None)
        title = next((label for _, key, label in NFC_FIELDS if key == field), 'NFC')
        options = getattr(self, '_nfc_choice_options', ())
        current = getattr(self._nfc_config(), field, None) if field else None
        confirmed = getattr(self, '_nfc_confirmed', {})
        entries = [('Back', self.ICON_Back, None, None)]
        for option in options:
            checked = option == current and (field == 'speed' or confirmed.get(field, False))
            entries.append((self._nfc_choice_label(option),
                            ICON_NFC if field == 'model' else self.ICON_Info,
                            checked, self._menu_checkbox_painter(checked)))
        if field == 'port' and not options:
            if getattr(self, '_nfc_port_future', None) is not None:
                message = 'Loading...'
            elif getattr(self, '_nfc_port_error', False):
                message = 'Unavailable'
            else:
                message = 'No devices'
            entries.append((message, self.ICON_Info, None, None))
        self._nfc_choice_selection = min(getattr(self, '_nfc_choice_selection', 0),
                                          len(entries) - 1)
        self._draw_list_menu(title, entries, self._nfc_choice_selection)

    def _nfc_apply_choice(self, field, selected):
        value = self._nfc_config()
        changed = getattr(value, field) != selected
        changes = {field: int(selected) if field == 'speed' else selected}
        if field == 'model' and changed:
            interface = PROFILES[selected]['interfaces'][0]
            changes.update(interface=interface, port='', speed=115200 if interface == 'UART' else 0)
            self._nfc_confirmed.update(interface=False, port=False)
        elif field == 'interface' and changed:
            changes.update(port='', speed=115200 if selected == 'UART' else 0)
            self._nfc_confirmed['port'] = False
        if field in ('model', 'interface', 'port'):
            self._nfc_confirmed[field] = True
        if field in ('model', 'interface') and changed:
            self._nfc_port_choices = None
        self._nfc_values = replace(value, **changes)
        self._nfc_save_error = False
        self._nfc_test_state = None

    def _nfc_exit_choice(self):
        pending = getattr(self, '_nfc_port_future', None)
        if pending is not None:
            pending.cancel()
        self._nfc_port_future = None
        self._nfc_choice_field = None
        self._nfc_choice_options = ()
        self._nfc_choice_selection = 0
        self.checkkey = self.NFCSettingsMenu
        self.Draw_NFC_Settings_Menu()
        self.lcd.update()

    def HMI_NFC_Choice_Menu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        options = getattr(self, '_nfc_choice_options', ())
        selection = getattr(self, '_nfc_choice_selection', 0)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            direction = 1 if event == self.ENCODER_DIFF_CW else -1
            delta = direction * max(1, int(getattr(self, '_rotation_steps', 1)))
            self._nfc_choice_selection = max(0, min(len(options), selection + delta))
            self.Draw_NFC_Choice_Menu()
            self.lcd.update()
            return
        if event == self.ENCODER_DIFF_ENTER:
            field = getattr(self, '_nfc_choice_field', None)
            if (0 < selection <= len(options) and field
                    and self._nfc_enabled() and self._nfc_field_enabled(field)):
                self._nfc_apply_choice(field, options[selection - 1])
            self._nfc_exit_choice()

    def _nfc_poll_test_connection(self):
        future = getattr(self, '_nfc_test_future', None)
        if future is None or not future.done():
            return False
        self._nfc_test_future = None
        try:
            success = future.result() is True
        except Exception as error:
            logging.warning('NFC connection test failed: %s', error)
            success = False
        self._nfc_test_state = 'OK' if success else 'Fail'
        if (getattr(self, 'checkkey', None) == self.NFCSettingsMenu
                and getattr(self, '_nfc_test_values', None) == self._nfc_config()):
            self.Draw_NFC_Settings_Menu()
            self.lcd.update()
        return True

    def HMI_NFC_Settings_Menu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        selection = getattr(self, '_nfc_selection', 0)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            direction = 1 if event == self.ENCODER_DIFF_CW else -1
            delta = direction * max(1, int(getattr(self, '_rotation_steps', 1)))
            self._nfc_selection = max(0, min(7, selection + delta))
        elif event == self.ENCODER_DIFF_ENTER:
            if selection == 0:
                self.checkkey = self.DisplayMenu
                self._display_selection = 4 + len(self._buzzer_rows())
                self.Draw_Display_Menu()
                self.lcd.update()
                return
            if not self._nfc_enabled() or selection not in self._nfc_focusable():
                # Read-only status and disabled settings are never activated.
                return
            field = next((field for row, field, _ in NFC_FIELDS if row == selection), None)
            if field:
                if self._nfc_open_choice(field):
                    self.lcd.update()
                return
            if selection == 7 and selection in self._nfc_focusable():
                if getattr(self, '_nfc_test_future', None) is not None:
                    return
                self._nfc_test_values = self._nfc_config()
                self._nfc_test_state = None
                try:
                    self._nfc_test_future = self.pd.test_nfc_connection(
                        self._nfc_test_values)
                except (OSError, ValueError) as error:
                    logging.warning('NFC connection test could not start: %s', error)
                    self._nfc_test_state = 'Fail'
                self.Draw_NFC_Settings_Menu()
                self.lcd.update()
                return
            if selection == 6 and selection in self._nfc_focusable():
                if getattr(self, '_nfc_test_future', None) is not None:
                    return
                try:
                    save(self._nfc_config())
                    self._nfc_saved = self._nfc_values
                    self._nfc_save_error = False
                    # NFC Core queues the backend reconfiguration asynchronously.
                    self.pd.reload_nfc_configuration()
                except (OSError, ValueError, TypeError):
                    self._nfc_save_error = True
        else:
            return
        self.Draw_NFC_Settings_Menu()
        self.lcd.update()
