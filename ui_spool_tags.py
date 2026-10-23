"""Spoolman inventory selection and NFC Core tag enrollment; LCD owner only."""
import textwrap

from lcd_resources import (ICON_LIBRARY_ID, ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST,
                           ICON_SPOOL, ICON_ASSIGN_TAG, ICON_NEXT_PAGE, ICON_RETRY,
                           ICON_NFC_INTERFACE, ICON_SAVE_PROFILE)
from spoolman_tags import PAGE_SIZE, BindingConflict


class SpoolTagViewMixin:
    def _spool_stop_scan_animation(self):
        lcd = getattr(self, '_spool_scan_lcd', None)
        self._spool_scan_lcd = None
        if lcd is not None and getattr(lcd, '_closed', False) is not True:
            lcd.configure_animation(3, False, ICON_LIBRARY_ID,
                                    ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST,
                                    56, 116, 20)

    def _spool_draw_scan_popup(self):
        lcd = self.lcd
        if getattr(self, '_spool_scan_lcd', None) is lcd:
            return  # Card/status events must not restart the native animation.
        self.Clear_Popup_Area()
        self.Draw_Title('Spool #%d' % self._spool_selected.id)
        lcd.draw_rectangle(1, lcd.Color_Bg_Window, 14, 72, 258, 361)
        lcd.draw_rectangle(0, lcd.Line_Color, 14, 72, 258, 361)
        lines = ('Assign spool tag', 'Hold spool near reader', 'Press to cancel')
        for y, label in zip((88, 291, 329), lines):
            lcd.draw_text(False, False, lcd.font8x16, lcd.Popup_Text_Color,
                          lcd.Color_Bg_Window, (272 - len(label) * 8) // 2, y, label)
        lcd.configure_animation(3, True, ICON_LIBRARY_ID,
                                ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST,
                                56, 116, 20)
        self._spool_scan_lcd = lcd

    def _spool_load(self, offset=0):
        self._rfid_cancel_assignment()
        self._spool_offset = offset
        self._spool_selection = 0
        self._rfid_mode = 'spool_loading'
        self._spool_future = self.pd.nfc_spool_page(offset)
        self._spool_future.add_done_callback(
            lambda future: self._queue_nfc_ui_event('nfc_spool_ready'))

    def _spool_result_event(self):
        future = getattr(self, '_spool_future', None)
        if future is None or not future.done():
            return
        self._spool_future = None
        mode = getattr(self, '_rfid_mode', '')
        if mode not in ('spool_loading', 'spool_saving'):
            return
        try:
            result = future.result()
            if mode == 'spool_loading':
                self._spool_rows, self._spool_more = result
                self._rfid_mode = 'spool_list'
            else:
                self._spool_message = 'Saved in Spoolman Tags'
                self._rfid_candidate = None
                self._rfid_mode = 'spool_saved'
        except BindingConflict as error:
            self._spool_plan = error.plan
            self._rfid_mode = 'spool_transfer'
        except Exception as error:
            self._spool_message = (str(error) if isinstance(error, ValueError)
                                   else 'Spoolman unavailable')[:90]
            self._rfid_mode = 'spool_error'
        self._spool_selection = 0
        # Complete state transitions under overlays; only drawing is deferred.
        if self._uart_online and self.checkkey == self.RFIDMenu:
            self.Draw_RFID_Menu()
            self.lcd.update()

    def _spool_capture_event(self):
        future = getattr(self, '_rfid_assignment', None)
        if future is None or not future.done():
            return
        self._rfid_assignment = None
        self._spool_stop_scan_animation()
        try:
            self._rfid_candidate = future.result()
        except Exception:
            self._rfid_mode = 'spool_detail'
        else:
            self._rfid_mode = 'spool_confirm'
        self._spool_selection = 0
        if self._uart_online and self.checkkey == self.RFIDMenu:
            self.Draw_RFID_Menu()
            self.lcd.update()

    def _spool_entries(self):
        rows = [('Back', self.ICON_Back, None, None)]
        choices = [('back', None)]
        if self._spool_offset:
            rows.append(('Previous page', self.ICON_Back, None, None))
            choices.append(('page', max(0, self._spool_offset - PAGE_SIZE)))
        for spool in getattr(self, '_spool_rows', ()):
            label = ('#%d %s' % (spool.id, spool.vendor))[:24]
            rows.append((label, ICON_SPOOL, spool, self._spool_row_painter(spool)))
            choices.append(('spool', spool))
        if getattr(self, '_spool_more', False):
            rows.append(('Next page', ICON_NEXT_PAGE, None, None))
            choices.append(('page', self._spool_offset + PAGE_SIZE))
        return rows, choices

    def _spool_row_painter(self, spool):
        def paint(row):
            y = self.MBASE(row)
            self._draw_menu_text((spool.material + ' ' + spool.name)[:20], 60, y + 18)
            self._spool_swatch(spool.colors, 234, y + 17, 22, 17)
        return paint

    def _spool_swatch(self, colors, x, y, width, height):
        if colors:
            for i, code in enumerate(colors):
                value = int(code, 16)
                rgb565 = ((value >> 19) & 31) << 11 | ((value >> 10) & 63) << 5 | (value >> 3) & 31
                left = x + i * width // len(colors)
                right = x + (i + 1) * width // len(colors) - 1
                self.lcd.draw_rectangle(1, rgb565, left, y, right, y + height)
        self.lcd.draw_rectangle(0, 0xC618, x, y, x + width - 1, y + height)
        if not colors:
            self.lcd.draw_line(0x8410, x, y, x + width - 1, y + height)

    @staticmethod
    def _spool_lines(value, width=31, limit=2):
        return textwrap.wrap(value, width=width, break_long_words=True,
                             break_on_hyphens=False)[:limit] or ['Unknown']

    def _spool_draw_summary(self, spool, compact=False):
        self._draw_menu_text(('#%d  %s' % (spool.id, spool.material))[:31], 8, 150)
        if compact:
            self._draw_menu_text(spool.vendor[:31], 8, 174)
            self._draw_menu_text(spool.name[:31], 8, 196)
            self._draw_menu_text(('Color ' + (' / '.join('#' + c for c in spool.colors) or 'Unknown'))[:26], 8, 218)
            self._spool_swatch(spool.colors, 230, 216, 28, 18)
            return
        self._draw_menu_text('Vendor', 8, 174)
        self._draw_menu_text(spool.vendor[:31], 8, 196)
        for i, line in enumerate(self._spool_lines(spool.name)):
            self._draw_menu_text(line, 8, 222 + i * 20)
        self._draw_menu_text(('Color ' + (' / '.join('#' + c for c in spool.colors) or 'Unknown'))[:31], 8, 266)
        self._spool_swatch(spool.colors, 8, 294, 248, 30)

    def _spool_draw(self):
        mode = self._rfid_mode
        if mode == 'spool_waiting':
            self._spool_draw_scan_popup()
            return
        self._spool_stop_scan_animation()
        selection = getattr(self, '_spool_selection', 0)
        if mode == 'spool_list':
            rows, _ = self._spool_entries()
            self._draw_list_menu('Spoolman spools', rows, selection)
            if not getattr(self, '_spool_rows', ()):
                self._draw_menu_text('No available spools', 8, 150)
            return
        if mode in ('spool_loading', 'spool_saving'):
            self._draw_list_menu('Spoolman',
                [('Back', self.ICON_Back, None, None)], 0)
            self._draw_menu_text('Loading...' if mode == 'spool_loading' else 'Saving...', 8, 150)
            return
        if mode in ('spool_error', 'spool_saved'):
            self._draw_list_menu('Spoolman', [
                ('Back', self.ICON_Back, None, None),
                ('Retry' if mode == 'spool_error' else 'Choose another spool',
                 ICON_RETRY if mode == 'spool_error' else ICON_SPOOL, None, None)], selection)
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 145, 263, 351)
            for i, line in enumerate(self._spool_lines(self._spool_message, limit=3)):
                self._draw_menu_text(line, 8, 154 + i * 22)
            return
        spool = self._spool_selected
        if mode == 'spool_transfer':
            plan = self._spool_plan
            self._draw_list_menu('Move spool tag?', [
                ('Cancel', self.ICON_Back, None, None),
                ('Move and assign', ICON_NFC_INTERFACE, None, None)], selection)
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 145, 263, 351)
            source_ids = ','.join('#%d' % item.id for item in plan.sources)
            self._draw_menu_text(('From ' + (source_ids or 'Unassigned'))[:31], 8, 150)
            self._draw_menu_text(('To #%d %s' % (spool.id, spool.vendor))[:31], 8, 174)
            self._draw_menu_text((spool.material + ' ' + spool.name)[:31], 8, 196)
            self._draw_menu_text('Replace existing tag' if plan.previous_uid not in (None, plan.uid)
                                 else 'Move tag to this spool', 8, 222)
            self._draw_menu_text('UID / ID', 8, 254)
            self._rfid_draw_uid(plan.uid, 278, 18)
            return
        waiting = mode == 'spool_waiting'
        confirm = mode == 'spool_confirm'
        rows = [('Cancel' if waiting or confirm else 'Back', self.ICON_Back, None, None)]
        if not waiting:
            rows.append(('Save tag' if confirm else 'Assign tag',
                         ICON_SAVE_PROFILE if confirm else ICON_ASSIGN_TAG, None, None))
        self._draw_list_menu('Save spool tag?' if confirm else 'Spool #%d' % spool.id, rows, selection)
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 145, 263, 351)
        if waiting:
            self._draw_menu_text('Present a new tag', 8, 104)
        self._spool_draw_summary(spool, compact=confirm)
        if confirm:
            self._draw_menu_text('UID / ID', 8, 254)
            self._rfid_draw_uid(self._rfid_candidate['uid'], 278, 18)

    def _spool_input(self, event):
        mode = self._rfid_mode
        selected = getattr(self, '_spool_selection', 0)
        if mode == 'spool_waiting':
            if event == self.ENCODER_DIFF_ENTER:
                self._rfid_cancel_assignment()
                self._spool_selection = 0
                self._list_render = None
                self.Draw_RFID_Menu()
                self.lcd.update()
            return
        if mode == 'spool_list':
            _, choices = self._spool_entries()
            maximum = len(choices) - 1
        else:
            maximum = 1 if mode in ('spool_detail', 'spool_confirm', 'spool_transfer', 'spool_error', 'spool_saved') else 0
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            direction = 1 if event == self.ENCODER_DIFF_CW else -1
            self._spool_selection = max(0, min(maximum, selected +
                direction * max(1, int(getattr(self, '_rotation_steps', 1)))))
        elif event == self.ENCODER_DIFF_ENTER:
            if selected == 0:
                self._rfid_cancel_assignment()
                pending = getattr(self, '_spool_future', None)
                if pending is not None:
                    pending.cancel()  # Never undo/replay a started server write.
                if mode in ('spool_confirm', 'spool_transfer', 'spool_waiting', 'spool_saved'):
                    self._rfid_mode = 'spool_detail'
                elif mode == 'spool_detail':
                    self._rfid_mode = 'spool_list'
                else:
                    self._rfid_mode = 'info'
                    self._rfid_selection = 2
                self._spool_selection = 0
            elif mode == 'spool_list':
                action, value = choices[selected]
                if action == 'page':
                    self._spool_load(value)
                else:
                    self._spool_selected = value
                    self._rfid_mode = 'spool_detail'
                    self._spool_selection = 0
            elif mode == 'spool_detail':
                core = self.pd.get_nfc_core()
                try:
                    if core is None or not core.is_ready():
                        raise OSError('NFC reader unavailable')
                    self._rfid_assignment = core.begin_assignment()
                    self._rfid_mode = 'spool_waiting'
                    self._spool_selection = 0
                    self._rfid_assignment.add_done_callback(
                        lambda future: self._queue_nfc_ui_event('nfc_emg_capture'))
                except OSError:
                    self._spool_message = 'NFC reader unavailable'
                    self._rfid_mode = 'spool_error'
            elif mode in ('spool_confirm', 'spool_transfer'):
                try:
                    self._spool_future = self.pd.nfc_assign_spool(
                        self._spool_selected, self._rfid_candidate['uid'],
                        **({'approval': self._spool_plan} if mode == 'spool_transfer' else {}))
                    self._rfid_mode = 'spool_saving'
                    self._spool_selection = 0
                    self._spool_future.add_done_callback(
                        lambda future: self._queue_nfc_ui_event('nfc_spool_ready'))
                except (OSError, ValueError) as error:
                    self._spool_message = str(error)[:90]
                    self._rfid_mode = 'spool_error'
                    self._spool_selection = 0
            else:
                self._spool_load(getattr(self, '_spool_offset', 0))
        else:
            return
        self.Draw_RFID_Menu()
        self.lcd.update()
