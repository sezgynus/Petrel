"""RFID card information and explicit emergency-tag enrollment on the LCD owner."""
import logging

from lcd_resources import ICON_NFC


class RFIDViewMixin:
    def _rfid_cancel_assignment(self):
        future = getattr(self, '_rfid_assignment', None)
        self._rfid_assignment = None
        if future is not None:
            future.cancel()
        self._rfid_candidate = None

    def _rfid_assignment_event(self):
        future = getattr(self, '_rfid_assignment', None)
        if (getattr(self, 'checkkey', None) != self.RFIDMenu
                or getattr(self, '_rfid_mode', 'info') != 'waiting'):
            self._rfid_cancel_assignment()
            return
        if future is None or not future.done():
            return
        self._rfid_assignment = None
        try:
            self._rfid_candidate = future.result()
        except Exception:
            self._rfid_message = 'Read failed'
            self._rfid_mode = 'emg'
        else:
            self._rfid_mode = 'confirm'
        self._rfid_selection = 0
        if self._uart_online:
            self.Draw_RFID_Menu()
            self.lcd.update()

    def Draw_RFID_Menu(self, full=True):
        mode = getattr(self, '_rfid_mode', 'info')
        if mode == 'info':
            self._draw_rfid_info(full)
            return
        core = self.pd.get_nfc_core()
        uid = core.global_action_uid('emergency_stop') if core else None
        if mode == 'waiting':
            self._draw_list_menu('Emergency stop tag', [
                ('Cancel', self.ICON_Back, None, None),
                ('Present a new tag', ICON_NFC, None, None)], 0)
            self._draw_menu_text('Remove and tap card', 8, 240)
            return
        if mode == 'confirm':
            self._draw_list_menu('Save emergency tag?', [
                ('Cancel', self.ICON_Back, None, None),
                ('Save tag', ICON_NFC, None, None)],
                getattr(self, '_rfid_selection', 0))
            uid = (getattr(self, '_rfid_candidate', None) or {}).get('uid')
        else:
            self._draw_list_menu('Emergency stop tag', [
                ('Back', self.ICON_Back, None, None),
                ('Replace tag' if uid else 'Assign tag', ICON_NFC, None, None),
                ('Remove tag', self.ICON_Info, None, None)],
                getattr(self, '_rfid_selection', 0))
            self._draw_menu_text(getattr(self, '_rfid_message', '') or
                                 ('Assigned' if uid else 'Not assigned'), 8, 240)
        # Preserve the entire UID, including long native identifiers.
        parts = (uid or '').split(':')
        for index in range(0, len(parts), 10):
            self._draw_menu_text(':'.join(parts[index:index + 10]), 8,
                                 272 + (index // 10) * 24)

    def _draw_rfid_info(self, full=True):
        # Initial render uses Core's last cached event; subsequent renders are
        # exclusively triggered by NFC events on the LCD owner's event queue.
        if full:
            self.pd.sync_nfc_event()
        state = self.pd.system_info.get('rfid') or {}
        status = state.get('status') or self.pd.system_info.get('nfc', {}).get('status', 'Reading...')
        card = state.get('card') or {}
        rows = (('Status', status, 132), ('Type', card.get('type', '-'), 164),
                ('ATQA', card.get('atqa', '-'), 316), ('SAK', card.get('sak', '-'), 340))
        old_rows, old_uid = getattr(self, '_rfid_render', ((), None))
        if full:
            self.Clear_Main_Window()
            self.Draw_Title('RFID')
            self.Draw_Back_First(getattr(self, '_rfid_selection', 0) == 0)
            self._draw_info_section('Last card', 100)
            self._draw_menu_text('UID / ID', 8, 188)
            old_rows, old_uid = (), None
        for index, (label, value, y) in enumerate(rows):
            if full:
                self._draw_info_row(label, value, y)
            elif index >= len(old_rows) or old_rows[index] != rows[index]:
                self._draw_info_value(label, value, y, clear=True)
        # Full-width UID lines preserve identifiers up to 32 bytes; never truncate identity.
        uid = card.get('uid', 'Waiting for card')
        if uid != old_uid:
            if not full:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 208, 263, 303)
            parts = uid.split(':')
            lines = [':'.join(parts[i:i+10]) for i in range(0, len(parts), 10)]
            for index, text in enumerate(lines[:4]):
                self._draw_menu_text(text, 8, 208 + index * 24)
        self._rfid_render = (rows, uid)

        if full:
            selected = getattr(self, '_rfid_selection', 0) == 1
            self._draw_menu_text(('> ' if selected else '  ') + 'Emergency stop tag', 8, 374)

    def HMI_RFID(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        mode = getattr(self, '_rfid_mode', 'info')
        selection = getattr(self, '_rfid_selection', 0)
        maximum = 0 if mode == 'waiting' else 2 if mode == 'emg' else 1
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            direction = 1 if event == self.ENCODER_DIFF_CW else -1
            self._rfid_selection = max(0, min(maximum, selection +
                direction * max(1, int(getattr(self, '_rotation_steps', 1)))))
        elif event == self.ENCODER_DIFF_ENTER:
            if mode == 'info':
                if selection == 0:
                    self._rfid_cancel_assignment()
                    self.select_page.set(next(i for i, entry in enumerate(self._home_entries())
                                              if entry[0] == 'RFID'))
                    self.Goto_MainMenu()
                    self.lcd.update()
                    return
                self._rfid_mode = 'emg'
                self._rfid_selection = 0
                self._rfid_message = ''
            elif mode == 'waiting' or selection == 0:
                self._rfid_cancel_assignment()
                self._rfid_mode = 'info' if mode == 'emg' else 'emg'
                self._rfid_selection = 0
            else:
                core = self.pd.get_nfc_core()
                try:
                    if core is None:
                        raise OSError('NFC disabled')
                    if mode == 'emg' and selection == 1:
                        if not core.is_ready():
                            raise OSError('Reader unavailable')
                        self._rfid_candidate = None
                        self._rfid_assignment = core.begin_assignment()
                        self._rfid_mode = 'waiting'
                        self._rfid_selection = 0
                        self._rfid_assignment.add_done_callback(
                            lambda future: self._queue_nfc_ui_event('nfc_emg_capture'))
                    elif mode == 'confirm':
                        core.assign_global_action('emergency_stop',
                            self._rfid_candidate['uid'])
                        self._rfid_candidate = None
                        self._rfid_message = 'Saved'
                        self._rfid_mode = 'emg'
                        self._rfid_selection = 0
                    elif mode == 'emg' and selection == 2:
                        core.remove_global_action('emergency_stop')
                        self._rfid_message = 'Removed'
                except (OSError, ValueError, TypeError, KeyError):
                    logging.exception('Emergency tag configuration failed')
                    self._rfid_message = 'Not saved / unavailable'
                    self._rfid_mode = 'emg'
                    self._rfid_selection = 0
        else:
            return
        self.Draw_RFID_Menu()
        self.lcd.update()
