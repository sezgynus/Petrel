"""Display buzzer enable/volume/tone preferences (pin fixed in Kconfig)."""
from dataclasses import replace
import logging
from ui_events import InputEvent
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

    def _play_buzzer_melody(self, name, *, priority=False):
        """Shared UI entry point for named scores; no event bindings implied."""
        settings = self._buzzer_settings()
        if not settings.enabled or (name != 'EMERGENCY' and not settings.volume):
            return False
        if getattr(self, '_buzzer_player', None) is None:
            self._buzzer_player = Player()
        return self._buzzer_player.play_melody(name, settings, priority=priority)

    def _queue_buzzer_melody(self, name, epoch):
        if (getattr(self, '_closed', False)
                or not getattr(self, '_event_buzzer_ready', False)):
            return
        loop = getattr(self, '_loop', None)
        if loop is not None:
            loop.post_coalesced(InputEvent('melody_' + name, 0, epoch))

    def _event_buzzer_melody(self, name):
        if (getattr(self, '_closed', False)
                or not getattr(self, '_event_buzzer_ready', False)):
            return False
        try:
            return self._play_buzzer_melody(name, priority=True)
        except (OSError, ValueError, RuntimeError):
            # Sound must never break printer control or WebSocket processing.
            logging.exception('Buzzer notification failed: %s', name)
            return False

    def _arm_buzzer_events(self):
        """Only use persisted preferences; UART reconnect never replays BOOT."""
        self._event_buzzer_ready = True
        self._maybe_play_boot_melody()

    def _maybe_play_boot_melody(self):
        """Join settings-ready and startup-complete events, without a timer."""
        if (getattr(self, '_boot_melody_attempted', False)
                or getattr(self, '_boot_active', False)
                or not getattr(self, '_event_buzzer_ready', False)
                or getattr(self, '_closed', False)):
            return False
        settings = self._buzzer_settings()
        if not settings.enabled or not settings.volume:
            # Explicit mute is intentional, not a sound to replay when unmuted.
            self._boot_melody_attempted = True
            logging.info('BOOT melody muted: enabled=%s volume=%s',
                         settings.enabled, settings.volume)
            return False
        accepted = bool(self._event_buzzer_melody('BOOT'))
        if accepted:
            self._boot_melody_attempted = True
            logging.info('BOOT melody queued: volume=%s', settings.volume)
        else:
            logging.warning('BOOT melody not queued; buzzer busy or unavailable')
        return accepted

    def _rfid_buzzer_feedback(self):
        # NFC beep uses the hardware buzzer but respects the global On/Off.
        # Its volume/tone remain deliberate independent notification defaults.
        if not self._buzzer_enabled():
            return
        if getattr(self, '_buzzer_player', None) is None:
            self._buzzer_player = Player()
        self._buzzer_player.play(Settings(enabled=True, volume=100, click=3), 'press', priority=True)

    def _emergency_buzzer_feedback(self):
        # Called directly by NFC Core's global emergency event, not the LCD
        # queue, so Klipper shutdown and an offline display cannot delay it.
        # Emergency is full-volume and preempts clicks/card beeps; the explicit
        # master Buzzer Off preference is still respected.
        if not self._buzzer_enabled():
            return
        if getattr(self, '_buzzer_player', None) is None:
            self._buzzer_player = Player()
        self._buzzer_player.play_emergency()

    def _subscribe_emergency_buzzer(self, core):
        return core.subscribe('action.emergency_stop',
                              lambda event: self._emergency_buzzer_feedback(),
                              priority=100)

    def _save_buzzer(self, values, *, toggle=False):
        """Persist to panel Flash; only verified readback commits the saved state."""
        if getattr(self, '_buzzer_save_future', None) is not None:
            raise RuntimeError('Buzzer save already pending')
        values.validate()
        if values != getattr(self, '_buzzer_saved', None):
            if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                self._panel_flash_lcd = self.lcd
                # begin_flash_write_verified may return an already-failed
                # Future (queue full / disconnected); handle it in the poll.
                self._buzzer_save_future = self.lcd.begin_flash_write_verified(
                    self.lcd.BUZZER_SETTINGS_ADDRESS, values.encode())
                self._buzzer_save_target = values
                self._buzzer_save_is_toggle = toggle
                self._display_save_message = 'Saving...'
                self._buzzer_values = values
            else:
                self.lcd.save_buzzer_settings(values)
                self._buzzer_values = self._buzzer_saved = values
                self._buzzer_save_error = False
                self._display_save_message = ''
        else:
            self._buzzer_values = values
            self._buzzer_save_error = False
            self._display_save_message = ''
        player = getattr(self, '_buzzer_player', None)
        if player is not None:
            player.cancel()
            if not values.enabled and hasattr(player, 'mute_external'):
                player.mute_external()

    def _buzzer_rows(self):
        settings = self._buzzer_settings()
        return [('Buzzer', 'Enabled' if settings.enabled else 'Disabled', True),
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
                self._save_buzzer(replace(self._buzzer_settings(), enabled=not self._buzzer_enabled()),
                                  toggle=True)
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
                    if getattr(self, '_buzzer_save_future', None) is None:
                        self._display_edit = False
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
