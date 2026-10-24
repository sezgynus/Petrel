"""Checkbox event preferences with verified Flash commit and rollback."""
import logging
from event_sound_settings import ADDRESS, RECORD_SIZE, EVENTS, EventSounds
from lcd_resources import ICON_BUZZER
from t5uic1_driver import T5UIC1ProtocolError


class EventSoundsViewMixin:
    def _event_sound_settings(self):
        value = getattr(self, '_event_sound_values', None)
        return value if isinstance(value, EventSounds) else EventSounds()

    def _event_sound_enabled(self, name):
        return (getattr(self, '_sound_event_prefs_ready', True)
                and getattr(self, '_buzzer_load_complete', True)
                and self._event_sound_settings().enabled(name))

    def _load_event_sound_preferences(self, asynchronous):
        self._event_sound_load_failed = False
        if getattr(self, '_event_sound_save_future', None) is not None:
            self._event_sound_save_future = None
            self._event_sound_values = getattr(self, '_event_sound_saved', EventSounds())
            self._event_sound_message = 'Not saved'
        if asynchronous:
            self._panel_flash_lcd = self.lcd
            self._event_sound_load_future = self.lcd.begin_flash_read(ADDRESS, RECORD_SIZE)
        else:
            try:
                self._adopt_event_sound_record(self.lcd.read_flash(ADDRESS, RECORD_SIZE))
            except (OSError, TimeoutError, T5UIC1ProtocolError):
                self._event_sound_load_failed = True
                self._event_sound_message = 'Read failed'
                logging.exception('Could not load event sound preferences')

    def _adopt_event_sound_record(self, raw):
        # Missing/invalid record is the first-install/upgrade default: all enabled.
        values = EventSounds.decode(raw) or EventSounds()
        self._event_sound_load_failed = False
        if getattr(self, '_event_sound_message', '') in ('Loading...', 'Read failed'):
            self._event_sound_message = ''
        self._event_sound_values = self._event_sound_saved = values
        self._sound_event_prefs_ready = True
        if getattr(self, '_buzzer_load_complete', False):
            self._arm_buzzer_events()

    def _poll_event_sound_flash(self):
        changed = False
        for kind in ('load', 'save'):
            attr = '_event_sound_' + kind + '_future'
            future = getattr(self, attr, None)
            if future is None or not future.done():
                continue
            setattr(self, attr, None)
            try:
                raw = future.result()
                if kind == 'load':
                    self._adopt_event_sound_record(raw)
                else:
                    if raw != self._event_sound_save_target.encode():
                        raise T5UIC1ProtocolError('Event sounds Flash readback mismatch')
                    self._event_sound_values = self._event_sound_saved = self._event_sound_save_target
                    self._event_sound_message = ''
            except Exception as error:
                if kind == 'load':
                    self._event_sound_load_failed = True
                    self._event_sound_message = 'Read failed'
                if kind == 'save':
                    self._event_sound_values = getattr(self, '_event_sound_saved', EventSounds())
                    self._event_sound_message = 'Not saved'
                logging.warning('Event sounds Flash %s failed: %s', kind, error)
            changed = True
        if changed and self.checkkey == self.EventSoundsMenu:
            self.Draw_Event_Sounds_Menu()
            self.lcd.update()

    def _toggle_event_sound(self, name):
        if getattr(self, '_event_sound_load_future', None) is not None:
            self._event_sound_message = 'Loading...'
            return
        if (not getattr(self, '_sound_event_prefs_ready', True)
                or getattr(self, '_event_sound_load_failed', False)):
            self._event_sound_message = 'Loading...'
            self._load_event_sound_preferences(
                getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True)
            return
        target = self._event_sound_settings().toggled(name)
        if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
            self._panel_flash_lcd = self.lcd
            self._event_sound_save_target = target
            self._event_sound_save_future = self.lcd.begin_flash_write_verified(ADDRESS, target.encode())
            self._event_sound_message = 'Saving...'
        else:
            raw = target.encode()
            self.lcd.write_flash(ADDRESS, raw)
            if self.lcd.read_flash(ADDRESS, RECORD_SIZE) != raw:
                raise T5UIC1ProtocolError('Event sounds Flash readback mismatch')
            self._event_sound_values = self._event_sound_saved = target
            self._event_sound_message = ''

    def Draw_Event_Sounds_Menu(self):
        pending = getattr(self, '_event_sound_save_future', None) is not None
        values = self._event_sound_save_target if pending else self._event_sound_settings()
        entries = [('Back', self.ICON_Back, None, None)]
        entries.extend((label, ICON_BUZZER, values.enabled(name),
                        self._menu_checkbox_painter(values.enabled(name)))
                       for name, label in EVENTS)
        self._event_sound_selection = max(0, min(len(EVENTS),
            getattr(self, '_event_sound_selection', 0)))
        message = getattr(self, '_event_sound_message', '')
        title = ('Sounds - saving...' if pending else
                 'Sounds - not saved' if message == 'Not saved' else
                 'Sounds - retry read' if message == 'Read failed' else
                 'Sounds - loading...' if getattr(self, '_event_sound_load_future', None) is not None
                 else 'Event sounds')
        self._draw_list_menu(title, entries, self._event_sound_selection)

    def HMI_Event_Sounds_Menu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO or getattr(self, '_event_sound_save_future', None) is not None:
            return
        selection = getattr(self, '_event_sound_selection', 0)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            delta = max(1, int(getattr(self, '_rotation_steps', 1)))
            if event == self.ENCODER_DIFF_CCW:
                delta = -delta
            self._event_sound_selection = max(0, min(len(EVENTS), selection + delta))
        elif event == self.ENCODER_DIFF_ENTER:
            if selection == 0:
                self.checkkey = self.DisplayMenu
                self._display_selection = 4 + len(self._buzzer_rows())
                self.Draw_Display_Menu()
                self.lcd.update()
                return
            try:
                self._toggle_event_sound(EVENTS[selection - 1][0])
            except (OSError, TimeoutError, T5UIC1ProtocolError):
                self._event_sound_message = 'Not saved'
                logging.exception('Event sound preference not saved')
        else:
            return
        self.Draw_Event_Sounds_Menu()
        self.lcd.update()
