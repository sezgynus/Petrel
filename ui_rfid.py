"""RFID card information and explicit emergency-tag enrollment on the LCD owner."""
import logging

from lcd_resources import (ICON_EMERGENCY_TAG, ICON_SPOOL, ICON_ASSIGN_TAG,
                           ICON_REMOVE_TAG, ICON_SAVE_PROFILE)
from ui_spool_tags import SpoolTagViewMixin
from ui_nfc_gate import NFCGateViewMixin


class RFIDViewMixin(SpoolTagViewMixin, NFCGateViewMixin):
    def _subscribe_nfc_card_notifications(self, core):
        # Observe before enrollment consumes the arrival, below emergency dispatch.
        return core.subscribe('card.detected',
            lambda card: self._queue_nfc_ui_event('nfc_card'), priority=500)

    def _rfid_context_active(self):
        """Temporary overlays retain the enrollment owned by their origin."""
        screen = getattr(self, 'checkkey', None)
        if screen == self.PowerConfirm:
            screen = getattr(self, '_power_origin', None)
        if screen == self.NFCGateMenu:
            screen = (getattr(self, '_nfc_gate_popup', None) or {}).get('origin')
        return screen == self.RFIDMenu

    def _rfid_cancel_assignment(self):
        self._spool_stop_scan_animation()
        future = getattr(self, '_rfid_assignment', None)
        self._rfid_assignment = None
        if future is not None:
            future.cancel()
        self._rfid_candidate = None
        # Real navigation/cancellation must not leave a nonfunctional wait page.
        mode = getattr(self, '_rfid_mode', '')
        if mode in ('waiting', 'spool_waiting'):
            self._rfid_mode = 'emg' if mode == 'waiting' else 'spool_detail'

    def _rfid_assignment_event(self):
        if (self._rfid_context_active()
                and getattr(self, '_rfid_mode', '') == 'spool_waiting'):
            self._spool_capture_event()
            return
        future = getattr(self, '_rfid_assignment', None)
        if (not self._rfid_context_active()
                or getattr(self, '_rfid_mode', 'info') != 'waiting'):
            self._rfid_cancel_assignment()
            return
        if future is None or not future.done():
            return
        self._rfid_assignment = None
        self._spool_stop_scan_animation()
        try:
            self._rfid_candidate = future.result()
        except Exception:
            self._rfid_message = 'Read failed'
            self._rfid_mode = 'emg'
        else:
            self._rfid_mode = 'confirm'
        self._rfid_selection = 0
        if self._uart_online and self.checkkey == self.RFIDMenu:
            self.Draw_RFID_Menu()
            self.lcd.update()

    def Draw_RFID_Menu(self, full=True):
        mode = getattr(self, '_rfid_mode', 'info')
        if mode.startswith('spool_'):
            self._spool_draw()
            return
        if mode == 'waiting':
            self._draw_tag_capture_popup('card', 'Emergency stop tag',
                ('Assign emergency tag', 'Hold card near reader', 'Press to cancel'))
            return
        self._spool_stop_scan_animation()
        if mode == 'info':
            self._draw_rfid_info(full)
            return
        core = self.pd.get_nfc_core()
        uid = core.global_action_uid('emergency_stop') if core else None
        if mode == 'confirm':
            self._draw_list_menu('Save emergency tag?', [
                ('Cancel', self.ICON_Back, None, None),
                ('Save tag', ICON_SAVE_PROFILE, None, None)],
                getattr(self, '_rfid_selection', 0))
            uid = (getattr(self, '_rfid_candidate', None) or {}).get('uid')
            details = ('New emergency tag',)
        else:
            rows = [
                ('Back', self.ICON_Back, None, None),
                ('Replace tag' if uid else 'Assign tag', ICON_ASSIGN_TAG, None, None),
            ]
            if uid:
                rows.append(('Remove tag', ICON_REMOVE_TAG, None, None))
            self._rfid_selection = min(getattr(self, '_rfid_selection', 0), len(rows) - 1)
            self._draw_list_menu('Emergency stop tag', rows, self._rfid_selection)
            details = (getattr(self, '_rfid_message', '') or
                       ('Assigned' if uid else 'Not assigned'),)
        # All content ends before STATUS_Y=360; four full UID lines fit.
        token = (mode, uid, details)
        if full or getattr(self, '_rfid_details', None) != token:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 198, 263, 351)
            for index, text in enumerate(details):
                self._draw_menu_text(text, 8, 204 + index * 22)
            if uid:
                self._draw_menu_text('UID / ID', 8, 244)
                self._rfid_draw_uid(uid, 268, 22)
            self._rfid_details = token

    def _rfid_draw_uid(self, uid, y, spacing=20):
        # 10 bytes = 29 characters: fits 232px; never truncate native identity.
        parts = uid.split(':')
        for index in range(0, len(parts), 10):
            self._draw_menu_text(':'.join(parts[index:index + 10]), 8,
                                 y + (index // 10) * spacing)

    def _draw_rfid_info(self, full=True):
        if full:
            self.pd.sync_nfc_event()
        self._draw_list_menu('NFC', [
            ('Back', self.ICON_Back, None, None),
            ('Emergency stop tag', ICON_EMERGENCY_TAG, None, None),
            ('Spoolman tag', ICON_SPOOL, None, None)],
            getattr(self, '_rfid_selection', 0))
        state = self.pd.system_info.get('rfid') or {}
        status = state.get('status') or self.pd.system_info.get('nfc', {}).get('status', 'Reading...')
        card = state.get('card') or {}
        rows = (('Status', status, 198), ('Type', card.get('type', '-'), 220))
        old_rows, old_uid = getattr(self, '_rfid_render', ((), None))
        if full:
            # Standard action rows occupy y=31..136. Details have their own
            # bounded area; selection changes never erase the dashboard.
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 193, 263, 351)
            self._draw_menu_text('UID / ID', 8, 264)
            old_rows, old_uid = (), None
        for index, (label, value, y) in enumerate(rows):
            if full:
                self._draw_info_row(label, value, y)
            elif index >= len(old_rows) or old_rows[index] != rows[index]:
                self._draw_info_value(label, value, y, clear=True)
        signature = (card.get('atqa', '-'), card.get('sak', '-'))
        if full or getattr(self, '_rfid_protocol', None) != signature:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 240, 263, 257)
            self._draw_menu_text(('ATQA %s  SAK %s' % signature)[:31], 8, 242)
            self._rfid_protocol = signature
        uid = card.get('uid', 'Waiting for card')
        if uid != old_uid:
            if not full:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 280, 263, 351)
            self._rfid_draw_uid(uid, 282, 18)
        self._rfid_render = (rows, uid)

    def HMI_RFID(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        mode = getattr(self, '_rfid_mode', 'info')
        selection = getattr(self, '_rfid_selection', 0)
        if mode.startswith('spool_'):
            self._spool_input(event)
            return
        core = self.pd.get_nfc_core()
        assigned = core.global_action_uid('emergency_stop') if core else None
        maximum = (0 if mode == 'waiting' else 2 if mode == 'info'
                   or (mode == 'emg' and assigned) else 1)
        selection = min(selection, maximum)
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
                if selection == 2:
                    self._spool_load()
                else:
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
                        self._rfid_assignment = core.begin_assignment(action='emergency_stop')
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
                        self._rfid_selection = 0
                except (OSError, ValueError, TypeError, KeyError):
                    logging.exception('Emergency tag configuration failed')
                    self._rfid_message = 'Not saved / unavailable'
                    self._rfid_mode = 'emg'
                    self._rfid_selection = 0
        else:
            return
        self.Draw_RFID_Menu()
        self.lcd.update()
