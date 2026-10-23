"""Display buzzer enable/volume/tone preferences (pin fixed in Kconfig)."""
from dataclasses import replace
from buzzer_control import Settings, Player, TONES
from t5uic1_driver import T5UIC1ProtocolError


class BuzzerViewMixin:
    def _buzzer_settings(self):
        value = getattr(self, '_buzzer_values', None)
        return value if isinstance(value, Settings) else Settings()

    def _buzzer_enabled(self):
        return self._buzzer_settings().enabled

    def _buzzer_feedback(self, kind):
        settings = self._buzzer_settings()
        if settings.enabled and settings.volume:
            if getattr(self, '_buzzer_player', None) is None:
                self._buzzer_player = Player()
            self._buzzer_player.play(settings, kind)

    def _rfid_buzzer_feedback(self):
        # Card acceptance beep ignores the UI sound-toggle and tone selection.
        if getattr(self, '_buzzer_player', None) is None:
            self._buzzer_player = Player()
        self._buzzer_player.play(Settings(enabled=True, volume=100, click=3), 'press', priority=True)

    def _save_buzzer(self, values):
        if getattr(self, '_buzzer_save_future', None) is not None:
            raise RuntimeError('Buzzer save already pending')
        if values != getattr(self, '_buzzer_saved', None):
            if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                self._buzzer_save_target = values
                self._panel_flash_lcd = self.lcd
                self._buzzer_save_future = self.lcd.begin_flash_write_verified(
                    self.lcd.BUZZER_SETTINGS_ADDRESS, values.encode())
                self._display_save_message = 'Saving...'
                self._buzzer_values = values
            else:
                self.lcd.save_buzzer_settings(values)
                self._buzzer_values = self._buzzer_saved = values
        else:
            self._buzzer_values = values
        player = getattr(self, '_buzzer_player', None)
        if player is not None:
            player.cancel()

    def _buzzer_rows(self):
        settings = self._buzzer_settings()
        return [('Buzzer', 'On' if settings.enabled else 'Off', True),
                ('Volume', str(settings.volume) + '%', True),
                ('Click tone', TONES[settings.click], True),
                ('Encoder tone', TONES[settings.encoder], True)]

    def _buzzer_display_input(self, event):
        if getattr(self, '_buzzer_save_future', None) is not None:
            return True
        if event == self.ENCODER_DIFF_NO:
            return False
        selection = getattr(self, '_display_selection', 0)
        if selection < 4 or selection > 7:
            return False
        if selection == 4 and event == self.ENCODER_DIFF_ENTER:
            try:
                self._save_buzzer(replace(self._buzzer_settings(), enabled=not self._buzzer_enabled()))
                self._display_save_message = ''
            except (OSError, TimeoutError, T5UIC1ProtocolError):
                self._display_save_message = 'Not saved. Press to retry'
            self.Draw_Display_Menu()
            self.lcd.update()
            return True
        if selection == 4:
            return False
        if getattr(self, '_display_edit', False):
            if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                delta = getattr(self, '_rotation_steps', 1) * (1 if event == self.ENCODER_DIFF_CW else -1)
                value = self._buzzer_settings()
                field = ('volume', 'click', 'encoder')[selection - 5]
                current = getattr(value, field)
                updated = max(0, min(100, current + delta * 10)) if field == 'volume' else (current + delta) % len(TONES)
                self._buzzer_values = replace(value, **{field: updated})
            elif event == self.ENCODER_DIFF_ENTER:
                try:
                    self._save_buzzer(self._buzzer_settings())
                    self._display_edit = False
                    self._display_save_message = ''
                except (OSError, TimeoutError, T5UIC1ProtocolError):
                    self._display_save_message = 'Not saved. Press to retry'
            self.Draw_Display_Menu()
            self.lcd.update()
            return True
        if event == self.ENCODER_DIFF_ENTER:
            self._display_edit = True
            self.Draw_Display_Menu()
            self.lcd.update()
            return True
        return False
