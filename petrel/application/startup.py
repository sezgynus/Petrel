"""Existing PetrelDisplay methods grouped by responsibility."""
from petrel.artwork.resources import ICON_BOOT_FIRST, ICON_BOOT_LAST
from petrel.ui.theme import show_icon as show_theme_icon
from petrel.artwork.resources import ICON_PROGRESS_TRACK, ICON_PROGRESS_FILL
import petrel.features.display_settings.settings as display_settings
import time
import logging
import petrel.features.buzzer.control as buzzer_control
from petrel.features.buzzer.control import Settings as BuzzerSettings
from petrel.hardware.dwin.startup import PanelProbe
from petrel.hardware.dwin.driver import T5UIC1Display, T5UIC1ProtocolError


class PanelStartupMixin:
    def _uart_failed(self):
        self._spool_scan_reconnect_stop = bool(getattr(self, '_spool_scan_reconnect_stop', False)
                                               or getattr(self, '_spool_scan_lcd', None))
        self._spool_scan_lcd = None
        self._power_hold_started = None
        self._remote_power_hold_active = False
        self._remote_power_hold_deadline = None
        if getattr(self, '_boot_active', False):
            self._boot_progress = -1
        if (getattr(self, 'checkkey', None) == self.PowerConfirm
                and getattr(self, '_power_origin', None) == self.MMUMenu):
            self.checkkey = self.MMUMenu
            self._power_origin = None
        if getattr(self, 'checkkey', None) in (self.MMUMenu, self.Tune, self.TuneEdit, self.PrintErrorDetails):
            self._power_focus = False
            self._mmu_canvas_page = None
        self._uart_online = False
        self._uart_epoch += 1
        now = time.monotonic()
        self._next_uart_retry = now + (.15 if now < getattr(self, '_uart_fast_until', 0) else 5)
        self._next_uart_probe = 0
        self._uart_probe_failures = 0
        if self.lcd is not None:
            self.lcd.close()
        self.lcd = None
        probe = getattr(self, '_panel_probe', None)
        if probe is not None:
            probe.close()
            self._panel_probe = None
        logging.warning('LCD UART unavailable; reconnect scheduled')

    def _reset_power_ui(self):
        """A relay cycle starts a new UI session; never replay old input/actions."""
        self.checkkey = self.MainMenu
        self._boot_active = True
        self._boot_connection_started = None
        self._boot_connection_delayed = False
        self._boot_files_started = (None, 0)
        self._boot_progress = -1
        for name in self.SELECTIONS:
            selection = getattr(self, name, None)
            if selection is not None:
                selection.reset()
        self._power_focus = False
        self._power_origin = None
        self._info_scroll = 0
        if getattr(self, '_nfc_share_popup', None):
            self._cancel_nfc_share_popup(redraw=False)
        self._case_light_live_pending = None
        self._case_light_live_refresh = False
        self._case_light_live_epoch = None
        self._case_light_live_future = None
        self._display_selection = 0
        self._display_edit = False
        self._display_save_message = ''
        pending = getattr(self, '_nfc_port_future', None)
        if pending is not None:
            pending.cancel()
        self._nfc_port_future = None
        self._nfc_choice_field = None
        self._nfc_choice_options = ()
        self._nfc_choice_selection = 0
        self._nfc_port_choices = None
        self._nfc_port_error = False
        future = getattr(self, '_nfc_test_future', None)
        if future is not None:
            future.cancel()
        self._nfc_test_future = None
        self._nfc_test_state = None
        self._nfc_test_values = None
        if hasattr(self, '_display_saved'):
            self._display_values = list(self._display_saved)
        self._mmu_canvas_page = None
        self._mmu_edit = None
        self._mmu_confirmation = None
        self._mmu_map_draft = None
        self._mmu_endless_draft = None
        self._mmu_spool_draft = None
        self._action_feedback = None
        self._stop_waiting = False
        self._pending_start = None
        self._start_error_visible = False
        self._acknowledged_terminal = None
        self.index_prepare = self.index_tune = self.index_control = self.MROWS
        self._live_jog_pending = None
        self._live_jog_future = None
        self._encoder_event = self.ENCODER_DIFF_NO
        self.last_status = None
        self.last_cardpercentValue = 101
        self.next_rts_update_ms = 0

    def _ui_lifecycle(self):
        reader = getattr(self.pd.subscription, 'lifecycle', None)
        if callable(reader):
            value = reader()
            if isinstance(value, dict) and 'epoch' in value:
                return value
        # Test doubles and legacy subscriptions retain their normal snapshot.
        return self.pd.subscription.snapshot()

    def _poll_panel_power(self):
        monitor = getattr(self, '_power_monitor', None)
        if monitor is None:
            return
        status = monitor.poll()
        snapshot = self._ui_lifecycle()
        device = self.pd.power_device.casefold()
        notified = snapshot.get('power_devices', {}).get(device)
        if monitor.available is False:
            notified = None
        serial = snapshot.get('power_off_serial', {}).get(device, 0)
        if (notified in ('on', 'off') and
                (notified != getattr(self, '_power_notification', None)
                 or serial != self._relay_off_serial)):
            status = notified
            monitor.status = notified
            self._power_notification = notified
        epoch = snapshot['epoch']
        event_cycle = serial != self._relay_off_serial
        transition = (status in ('on', 'off') and status != self._relay_status
                      and (status == 'off' or self._relay_status is not None))
        # Klipper's epoch covers cycles missed while its WebSocket was down.
        backend_cycle = (snapshot['state'] == 'ready' and epoch != self._panel_backend_epoch
                         and not getattr(self, '_boot_active', False))
        if event_cycle or transition or backend_cycle:
            probe = getattr(self, '_panel_probe', None)
            if probe is not None:
                probe.close()
                self._panel_probe = None
            self._reset_power_ui()
            if self.lcd is not None:
                self.lcd.close()
                self.lcd = None
            self._uart_online = False
            self._uart_epoch += 1
            self._next_uart_retry = 0
            self._uart_probe_failures = 0
            logging.info('Printer power/session changed; starting fresh panel session')
        self._relay_off_serial = serial
        if status in ('on', 'off'):
            self._relay_status = status
        if snapshot['state'] == 'ready':
            self._panel_backend_epoch = epoch
        if hasattr(self, '_uart_start_signal'):
            available = True if notified in ('on', 'off') else monitor.available
            signal = (('power', serial) if available is True and status == 'on' else
                      ('backend', epoch) if available is False and snapshot['state'] == 'ready' else None)
            if signal != self._uart_start_signal:
                self._uart_start_signal = signal
                if signal is not None and not self._uart_online:
                    self._uart_fast_until = time.monotonic() + 10
                    self._next_uart_retry = 0
                    if hasattr(self, '_loop'):
                        self._loop.set_interval(.05)
                    probe = getattr(self, '_panel_probe', None)
                    if probe is not None:
                        probe.accelerate()

    def _ensure_uart(self):
        if getattr(self, '_relay_status', None) == 'off':
            return False
        if self._uart_online:
            return True
        if self._closed or time.monotonic() < self._next_uart_retry:
            return False
        try:
            options = {}
            if hasattr(self, '_panel_probe'):
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
                if self._panel_probe is None:
                    self._panel_probe = PanelProbe(self._settings[0])
                    if time.monotonic() < self._uart_fast_until:
                        self._panel_probe.accelerate()
                port = self._panel_probe.poll()
                if port is None:
                    return False
                self._panel_probe.close()
                self._panel_probe = None
                options['connected_serial'] = port
            if getattr(self, '_emulator', None) is not None:
                options['packet_observer'] = self._emulator
            if getattr(self, '_boot_active', False):
                options['startup_progress'] = lambda lcd, value: self._draw_boot_progress(value, lcd)
            self.lcd = T5UIC1Display(self._settings[0], handshake_timeout=1.0,
                                 handshake_attempts=1, **options)
            if getattr(self, '_spool_scan_reconnect_stop', False):
                from petrel.artwork.resources import ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST
                first, last = getattr(self, '_spool_scan_range',
                    (ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST))
                self.lcd.configure_animation(3, False, self.ICON, first, last, 56, 116, 20)
                self._spool_scan_reconnect_stop = False
            async_flash = (getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH',
                                   None) is True)
            if async_flash:
                # Do not hold the UI owner during Flash reads. The defaults
                # remain usable until the verified panel records arrive.
                if not hasattr(self, '_display_values'):
                    self._display_values = [100, 0, 10]
                    self._display_saved = (100, 0, 10)
                if not hasattr(self, '_buzzer_values'):
                    self._buzzer_values = self._buzzer_saved = BuzzerSettings()
                self._panel_flash_lcd = self.lcd
                if not getattr(self, '_display_load_complete', False):
                    self._display_load_future = self.lcd.begin_flash_read(
                        self.lcd.DISPLAY_SETTINGS_ADDRESS,
                        self.lcd.DISPLAY_SETTINGS_SIZE)
                # Every new LCD connection needs a fresh persistent read:
                # an interrupted Flash transaction must not leave an unsaved
                # On/Off value masquerading as the saved preference.
                pending_buzzer = getattr(self, '_buzzer_save_future', None) is not None
                if pending_buzzer:
                    if getattr(self, '_buzzer_save_is_toggle', False):
                        self._buzzer_values = self._buzzer_saved
                    self._buzzer_save_future = None
                    self._buzzer_save_error = True
                    self._display_save_message = 'Not saved. Press to retry'
                self._event_buzzer_ready = False
                self._buzzer_load_complete = False
                self._buzzer_load_future = self.lcd.begin_flash_read(
                    buzzer_control.ADDRESS, buzzer_control.RECORD_SIZE)
                if getattr(self, '_display_save_future', None) is not None:
                    self._display_save_future = None
                    self._display_save_message = 'Not saved. Press to retry'
            else:
                if not hasattr(self, '_display_values'):
                    try:
                        values = self.lcd.load_display_settings()
                    except (OSError, TimeoutError, T5UIC1ProtocolError):
                        logging.warning('Unable to read display settings', exc_info=True)
                        values = None
                    if isinstance(values, tuple) and len(values) == 2:
                        values = values + (10,)
                    if not isinstance(values, tuple) or len(values) != 3:
                        values = None
                    self._display_values = list(values or (100, 0, 10))
                    self._display_saved = tuple(values or (100, 0, 10))
                if not hasattr(self, '_buzzer_values'):
                    try:
                        values = self.lcd.load_buzzer_settings()
                        buzzer_read_ok = True
                    except (OSError, TimeoutError, T5UIC1ProtocolError):
                        logging.warning('Buzzer settings unavailable; sounds disabled')
                        values = None
                        buzzer_read_ok = False
                    self._buzzer_values = values if isinstance(values, BuzzerSettings) else BuzzerSettings()
                    self._buzzer_saved = self._buzzer_values
                    if buzzer_read_ok:
                        self._buzzer_load_complete = True
                        self._arm_buzzer_events()
            self._load_event_sound_preferences(async_flash)
            self._display_last_activity = time.monotonic()
            self._display_dimmed = False
            self.lcd.set_backlight(display_settings.raw_brightness(self._display_values[0]))
            self._configure_menus()
            if getattr(self, '_boot_active', False):
                self._draw_boot_progress(70)
            else:
                self.HMI_StartFrame(False)
            if getattr(self, 'checkkey', None) == self.BedMeshScreen:
                self.Draw_Bed_Mesh()
            elif getattr(self, 'checkkey', None) == self.MeshProfiles:
                self.Draw_Mesh_Profiles()
            elif getattr(self, 'checkkey', None) == self.BedMeshMenu:
                self.Draw_Bed_Mesh_Menu()
            if getattr(self, 'checkkey', None) == self.MMUMenu:
                self._mmu_canvas_page = None
                self.Draw_MMU_Menu()
            elif getattr(self, 'checkkey', None) == self.Tune:
                self.Draw_Tune_Menu()
            elif getattr(self, 'checkkey', None) == self.TuneEdit:
                self._focus_edit_draw()
            elif getattr(self, 'checkkey', None) == self.PrintErrorDetails:
                self._focus_error_draw()
            if getattr(self, 'checkkey', None) == self.FilePreview:
                self.Draw_File_Preview()
            if getattr(self, 'checkkey', None) == self.EventSoundsMenu:
                self.Draw_Event_Sounds_Menu()
            elif getattr(self, 'checkkey', None) == self.DisplayMenu:
                self.Draw_Display_Menu()
            if getattr(self, 'checkkey', None) == self.MaintenanceMenu:
                self.Draw_Maintenance_Menu()
            if getattr(self, 'checkkey', None) == self.NFCSettingsMenu:
                self.Draw_NFC_Settings_Menu()
            if getattr(self, 'checkkey', None) == self.NFCChoiceMenu:
                self.Draw_NFC_Choice_Menu()
            if getattr(self, 'checkkey', None) == self.RecoveryScreen:
                self.Clear_Popup_Area()
                self._recovery_render = None
                self.Draw_Recovery()
            self.lcd.update()
            if (self.pd.connection_error and self.checkkey != self.MMUMenu
                    and not getattr(self, '_boot_active', False)):
                self._poll_recovery_ui()
            self._uart_online = True
            if hasattr(self, '_loop'):
                self._loop.set_interval(.5)
            self._uart_epoch += 1
            self._uart_probe_failures = 0
            self._next_uart_probe = time.monotonic() + 2.0
            if getattr(self, '_boot_active', False):
                self._poll_boot()
            logging.info('LCD UART connected; %s', 'boot readiness pending'
                         if getattr(self, '_boot_active', False) else 'current screen restored')
            return True
        except (OSError, TimeoutError):
            self._uart_failed()
            return False

    def _draw_progress_track(self, lcd, x, y, width, value, *, use_icons=True):
        # Text-free managed caps work on panels without opcode 0x08.
        from petrel.artwork.resources import ICON_PROGRESS_TRACK, ICON_PROGRESS_FILL
        def capsule(length, color, icon):
            length = min(width, max(8, length))
            if not use_icons:
                # Resident IDs may still belong to the previous directory.
                lcd.draw_rectangle(1, color, x, y, x + length - 1, y + 7)
                return
            show_theme_icon(lcd, self.ICON, icon, x, y)
            if length > 8:
                show_theme_icon(lcd, self.ICON, icon, x + length - 8, y)
                lcd.draw_rectangle(1, color, x + 4, y, x + length - 5, y + 7)
        capsule(width, 0x39C8, ICON_PROGRESS_TRACK)
        filled = max(0, min(width, round(width * value / 100)))
        if filled:
            capsule(filled, 0x063B, ICON_PROGRESS_FILL)

    def _draw_boot_progress(self, value, lcd=None, message=None):
        lcd = self.lcd if lcd is None else lcd
        message = message or {40: 'Preparing display assets', 70: 'Waiting for printer...',
                              80: 'Reading printer status', 90: 'Preparing menus',
                              100: 'Starting interface'}.get(value, 'Starting display')
        message = message[:27]
        value = max(getattr(self, '_boot_progress', -1), min(100, value))
        if (value == getattr(self, '_boot_progress', -1)
                and message == getattr(self, '_boot_message', None)
                and lcd is getattr(self, '_boot_animation_lcd', None)):
            return
        if lcd is getattr(self, '_boot_animation_lcd', None) and getattr(self, '_boot_animation_running', False):
            lcd.configure_animation(0, False, getattr(self, '_boot_animation_active_library', self.ICON), ICON_BOOT_FIRST, ICON_BOOT_LAST, self._boot_animation_x, 320, 10)
        self._boot_progress, self._boot_message = value, message
        # Restore original splash pixels; no solid-color patches over the artwork.
        lcd.copy_cache(0, 16, 284, 255, 344, 16, 284, background=True, enhanced=False)
        library = getattr(lcd, '_boot_animation_library', self.ICON)
        self._draw_progress_track(lcd, 24, 292, 224, value, use_icons=library is not None)
        x = (272 - (len(message)*8 + 24)) // 2
        lcd.draw_text(False, False, lcd.font8x16, 0xE75E, 0,
                      x+24, 322, message)
        self._boot_animation_running = value < 100 and library is not None
        if self._boot_animation_running:
            lcd.configure_animation(0, True, library, ICON_BOOT_FIRST, ICON_BOOT_LAST, x, 320, 10)
        self._boot_animation_active_library = library
        self._boot_animation_x, self._boot_animation_lcd = x, lcd
        lcd.update()

    def _poll_boot(self):
        snapshot = self.pd.subscription.snapshot()
        if snapshot['state'] != 'ready':
            self._update_ui_state()
            if not self._poll_recovery_ui():
                kind = getattr(getattr(self.pd, 'recovery', None), 'state', None)
                message = ('Starting Klipper...' if getattr(kind, 'kind', None) == 'startup'
                           else 'Connecting to printer...')
                self._draw_boot_progress(70, message=message)
            return
        self._draw_boot_progress(80)
        self._update_ui_state()
        snapshot = self.pd.subscription.snapshot()
        if (snapshot['state'] != 'ready' or self.pd.connection_error
                or not self.pd.state.ready or self.pd.state.epoch != snapshot['epoch']):
            self._draw_boot_progress(80, message='Waiting for printer data')
            return
        self.pd.prefetch_files()
        epoch, started = getattr(self, '_boot_files_started', (None, 0))
        if epoch != snapshot['epoch']:
            started = time.monotonic()
            self._boot_files_started = (snapshot['epoch'], started)
        if ((self.pd._files_loading is True or self.pd._directory_loading is True)
                and not self.pd.file_error
                and time.monotonic() - started < 5.0):
            self._draw_boot_progress(90, message='Preparing file list')
            return
        self._draw_boot_progress(90)
        self._configure_menus()
        self.pd.mmu_session.update()
        self._draw_boot_progress(100)
        self._boot_active = False
        self._maybe_play_boot_melody()
        self._uart_epoch += 1
        self._offline = False
        self._panel_backend_epoch = snapshot['epoch']
        self.HMI_StartFrame(False)
        self._display_last_activity = time.monotonic()
        self.lcd.update()

    def _poll_panel_flash(self):
        """Collect completed Flash futures on the same UART-owning UI thread."""
        if getattr(self, '_panel_flash_lcd', None) is not self.lcd:
            return
        self._poll_event_sound_flash()
        changed = False
        for kind in ('display_load', 'buzzer_load', 'display_save', 'buzzer_save'):
            attr = '_' + kind + '_future'
            future = getattr(self, attr, None)
            if future is None or not future.done():
                continue
            setattr(self, attr, None)
            try:
                raw = future.result()
                if kind == 'display_load':
                    values = display_settings.decode(raw)
                    if isinstance(values, tuple) and len(values) == 2:
                        values = values + (10,)
                    if isinstance(values, tuple) and len(values) == 3:
                        old = self._display_saved
                        if (tuple(self._display_values) == old
                                and not getattr(self, '_display_edit', False)
                                and getattr(self, '_display_save_future', None) is None):
                            self._display_values = list(values)
                            if not getattr(self, '_display_dimmed', False):
                                self.lcd.set_backlight(display_settings.raw_brightness(values[0]))
                        self._display_saved = values
                    self._display_load_complete = True
                elif kind == 'buzzer_load':
                    settings = BuzzerSettings.decode(raw)
                    if isinstance(settings, BuzzerSettings):
                        if (self._buzzer_values == self._buzzer_saved
                                and getattr(self, '_buzzer_save_future', None) is None):
                            self._buzzer_values = settings
                        self._buzzer_saved = settings
                        if not settings.enabled:
                            player = getattr(self, '_buzzer_player', None)
                            if player is not None and hasattr(player, 'mute_external'):
                                player.mute_external()
                    self._buzzer_load_complete = True
                    self._arm_buzzer_events()
                elif kind == 'display_save':
                    self._display_saved = self._display_save_target
                    self._display_edit = False
                    self._display_save_message = ''
                else:
                    # Only the exact verified bytes may be adopted as saved.
                    if raw != self._buzzer_save_target.encode():
                        raise T5UIC1ProtocolError('Buzzer Flash readback mismatch')
                    self._buzzer_saved = self._buzzer_save_target
                    self._buzzer_save_error = False
                    self._buzzer_save_is_toggle = False
                    if getattr(self, '_display_selection', None) in (5, 6, 7):
                        self._display_edit = False
                    self._display_save_message = ''
            except Exception as error:
                if kind == 'display_save':
                    # Failed Flash writes must not trap the encoder in an
                    # editor. Restore the last verified setting, then let the
                    # user navigate away or press again to start a new edit.
                    self._display_values = list(self._display_saved)
                    self._display_edit = False
                    if not getattr(self, '_display_dimmed', False):
                        self.lcd.set_backlight(
                            display_settings.raw_brightness(self._display_saved[0]))
                    self._display_save_message = 'Not saved. Press to retry'
                    logging.warning('Display settings Flash save failed: %s', error)
                elif kind == 'buzzer_save':
                    self._buzzer_save_error = True
                    self._buzzer_values = self._buzzer_saved
                    self._buzzer_save_is_toggle = False
                    self._display_edit = False
                    self._display_save_message = 'Not saved. Press to retry'
                    logging.warning('Buzzer settings Flash save failed: %s', error)
                else:
                    logging.warning('Could not read panel %s: %s', kind, error)
            changed = True
        if changed:
            if getattr(self, 'checkkey', None) == self.DisplayMenu:
                self.Draw_Display_Menu()
                self.lcd.update()
            elif getattr(self, 'checkkey', None) == self.NFCSettingsMenu:
                self.Draw_NFC_Settings_Menu()
                self.lcd.update()
