"""Display menu NFC reader configuration."""
from dataclasses import replace

from lcd_resources import ICON_NFC

from nfc_settings import (BAUD_RATES, NFCSettings, PROFILES,
                          available_ports, installed_enabled, load, save)


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

    def _nfc_field_enabled(self, field):
        confirmed = getattr(self, '_nfc_confirmed', {})
        if field == 'model':
            return True
        if field == 'interface':
            return confirmed.get('model', False)
        if field == 'port':
            return confirmed.get('interface', False) and bool(self._nfc_options('port'))
        if field == 'speed':
            return (confirmed.get('port', False)
                    and self._nfc_config().interface == 'UART')
        return False

    def _nfc_focusable(self):
        fields = {2: 'model', 3: 'interface', 4: 'port', 5: 'speed'}
        result = [0]
        result.extend(row for row, field in fields.items() if self._nfc_field_enabled(field))
        value = self._nfc_config()
        if (all(getattr(self, '_nfc_confirmed', {}).get(field, False)
                for field in ('model', 'interface', 'port'))
                and value.port in self._nfc_options('port')):
            result.append(6)
        return result

    def _nfc_options(self, field):
        value = self._nfc_config()
        if field == 'model':
            return tuple(PROFILES)
        if field == 'interface':
            return PROFILES[value.model]['interfaces']
        if field == 'port':
            return available_ports(value.interface, value.model)
        if field == 'speed':
            if value.interface == 'UART':
                return BAUD_RATES
        return ()

    def _nfc_value_text(self, field):
        value = self._nfc_config()
        current = getattr(value, field)
        if field == 'model' or field == 'interface':
            return str(current)
        if field == 'port':
            choices = self._nfc_options('port')
            return str(current) if current in choices else ('Select' if choices else 'Unavailable')
        if value.interface != 'UART':
            return 'Not applicable'
        return f'{current} baud'

    def Draw_NFC_Settings_Menu(self):
        enabled = self._nfc_enabled()
        value = self._nfc_config()
        status = 'Enabled' if enabled else 'Disabled in setup'
        rows = [('Back', self.ICON_Back, None, None),
                ('NFC feature', ICON_NFC, status, lambda row: self.lcd.draw_text(
                    True, False, self.lcd.font8x16, self.lcd.Color_White,
                    self.lcd.Color_Bg_Black, 120, self.MBASE(row) + 17, status))]
        for field, label in (('model', 'RFID module'), ('interface', 'Interface'),
                             ('port', 'Port / device'), ('speed', 'Link speed')):
            text = self._nfc_value_text(field)
            editing = getattr(self, '_nfc_edit', False) and getattr(self, '_nfc_selection', 0) == len(rows)
            active = enabled and self._nfc_field_enabled(field)
            painter = lambda row, text=text, editing=editing, active=active: self.lcd.draw_text(
                True, False, self.lcd.font8x16, self.lcd.Color_White if active else 0x8410,
                self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black,
                self.LBLX, self.MBASE(row) + 17, text[:25])
            shown_label = label if active else label + ' (disabled)'
            rows.append((shown_label, self.ICON_Info, (text, editing), painter))
        save_enabled = 6 in self._nfc_focusable()
        rows.append(('Save' if save_enabled else 'Save (disabled)', self.ICON_Info,
                     'Saved' if value == getattr(self, '_nfc_saved', value) else 'Apply', None))
        self._nfc_selection = min(getattr(self, '_nfc_selection', 0), len(rows) - 1)
        if not enabled:
            self._nfc_selection = 0
            rows = [rows[0]] + [(label if '(disabled)' in label else label + ' (disabled)', icon, shown, painter)
                                for label, icon, shown, painter in rows[1:]]
        title = 'NFC Settings - not saved' if getattr(self, '_nfc_save_error', False) else 'NFC Settings'
        self._draw_list_menu(title, rows, self._nfc_selection)

    def _nfc_change(self, field, direction):
        value = self._nfc_config()
        options = self._nfc_options(field)
        if not options:
            return
        current = getattr(value, field)
        if field == 'port' and current not in options:
            index = -1
        else:
            try:
                index = options.index(current)
            except ValueError:
                index = -1
        updated = options[(index + direction) % len(options)]
        changes = {field: updated}
        if field == 'model':
            interface = PROFILES[updated]['interfaces'][0]
            changes.update(interface=interface, port='', speed=115200 if interface == 'UART' else 0)
            self._nfc_confirmed.update(model=False, interface=False, port=False)
        elif field == 'interface':
            changes.update(port='', speed=115200 if updated == 'UART' else 0)
            self._nfc_confirmed.update(interface=False, port=False)
        elif field == 'port':
            # A bus/device change invalidates the previously selected rate only
            # when the interface class itself changes (handled above).
            pass
        elif field == 'speed':
            changes['speed'] = int(updated)
        self._nfc_values = replace(value, **changes)
        self._nfc_save_error = False

    def HMI_NFC_Settings_Menu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        if not self._nfc_enabled():
            self._nfc_selection = 0
            if event == self.ENCODER_DIFF_ENTER:
                self.checkkey = self.DisplayMenu
                self._display_selection = 4 + len(self._buzzer_rows())
                self.Draw_Display_Menu()
                self.lcd.update()
            return
        selection = getattr(self, '_nfc_selection', 0)
        editing = getattr(self, '_nfc_edit', False)
        row_fields = {2: 'model', 3: 'interface', 4: 'port', 5: 'speed'}
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            direction = 1 if event == self.ENCODER_DIFF_CW else -1
            if editing and selection in row_fields:
                self._nfc_change(row_fields[selection], direction)
            elif not editing:
                focusable = self._nfc_focusable()
                position = focusable.index(selection) if selection in focusable else 0
                position = max(0, min(len(focusable) - 1, position + direction * max(
                    1, int(getattr(self, '_rotation_steps', 1)))))
                self._nfc_selection = focusable[position]
        elif event == self.ENCODER_DIFF_ENTER:
            if selection == 0:
                self._nfc_edit = False
                self.checkkey = self.DisplayMenu
                self._display_selection = 4 + len(self._buzzer_rows())
                self.Draw_Display_Menu()
                self.lcd.update()
                return
            if selection in row_fields:
                field = row_fields[selection]
                if not self._nfc_field_enabled(field):
                    return
                self._nfc_edit = not editing
                if editing:
                    self._nfc_confirmed[field] = True
                    if field == 'model':
                        self._nfc_confirmed.update(interface=False, port=False)
                    elif field == 'interface':
                        self._nfc_confirmed['port'] = False
            elif selection == 6:
                if selection not in self._nfc_focusable():
                    return
                try:
                    save(self._nfc_config())
                    self._nfc_saved = self._nfc_values
                    self._nfc_save_error = False
                    reader = getattr(self.pd, '_rfid_reader', None)
                    if reader is not None:
                        reader.close()
                        self.pd._rfid_reader = None
                        self.pd._rfid_token = None
                    self._nfc_edit = False
                except (OSError, ValueError, TypeError):
                    self._nfc_save_error = True
        else:
            return
        self.Draw_NFC_Settings_Menu()
        self.lcd.update()
