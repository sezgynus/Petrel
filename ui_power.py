"""Global release-to-confirm power shortcut; GPIO callbacks only enqueue."""
import time
from concurrent.futures import Future
from ui_events import InputEvent
from graphite_theme import show_icon
from lcd_resources import ICON_POWER_HOLD_PANEL


class PowerShortcutMixin:
    POWER_OFF_HOLD_MS = 1200
    SHORT_PRESS_MS = 450

    def _power_button_down(self):
        with self._input_lock:
            now = time.monotonic()
            if (getattr(self, '_button_started_at', None) is not None
                    or now - self._last_press < self.ENCODER_WAIT_ENTER / 1000):
                return
            self._last_press = self._button_started_at = now
            snapshot = self._ui_lifecycle()
            self._button_origin = (snapshot['epoch'], getattr(self, '_uart_epoch', 0))
            self._button_can_power_off = (
                getattr(self, '_uart_online', True)
                and not getattr(self, '_boot_active', False)
                and getattr(self, '_relay_status', None) != 'off'
                and (snapshot['state'] == 'ready' or self.checkkey == self.MMUMenu))
            if self._button_can_power_off:
                self._loop.post(InputEvent('button_down', int(now * 1000), *self._button_origin))

    def _button_released(self):
        with self._input_lock:
            started = getattr(self, '_button_started_at', None)
            if started is None:
                return
            self._button_started_at = None
            elapsed = max(0, round((time.monotonic() - started) * 1000))
            eligible = self._button_can_power_off
            epoch, ui_epoch = self._button_origin
        # A long power-on press must not become Enter after reconnection.
        if not eligible and elapsed >= self.SHORT_PRESS_MS:
            return
        self._loop.post(InputEvent('button_release', elapsed, epoch, ui_epoch))

    def _clear_power_hold(self, restore=True, *, cancelled=True):
        visible = getattr(self, '_power_hold_visible', False)
        if visible and cancelled:
            self._event_buzzer_melody('POWER_HOLD_CANCEL')
        self._power_hold_started = None
        self._remote_power_hold_active = False
        self._remote_power_hold_deadline = None
        self._power_hold_visible = False
        if visible and restore:
            self._power_origin = self.checkkey
            self._restore_power_origin()
        if hasattr(self, '_loop'):
            self._loop.set_interval(.5)

    def _power_button_input(self, event):
        if event.kind == 'remote_button_down':
            if getattr(self, '_power_hold_started', None) is not None:
                return True  # A remote press must never release a physical hold.
            self._remote_power_hold_active = True
            self._remote_power_hold_deadline = time.monotonic() + 10.0
            event = InputEvent('button_down', int(time.monotonic() * 1000),
                               event.epoch, event.ui_epoch)
        elif event.kind == 'remote_button_release':
            if not getattr(self, '_remote_power_hold_active', False):
                return True  # Late or rejected releases cannot become Enter.
            event = InputEvent('button_release', event.value,
                               event.epoch, event.ui_epoch)
        elif event.kind == 'remote_button_cancel':
            if getattr(self, '_remote_power_hold_active', False):
                self._clear_power_hold()
                self.lcd.update()
            return True
        if event.kind == 'button_down':
            self._power_hold_started = event.value / 1000
            self._power_hold_epoch = event.epoch
            self._power_hold_pixels = 0
            self._power_hold_ready = False
            self._power_hold_visible = False
            self._power_wake_only = self._display_activity()
            self._loop.set_interval(.02)
            return True
        if event.kind != 'button_release':
            return False
        wake_only = getattr(self, '_power_wake_only', False)
        self._power_wake_only = False
        completed = event.value >= self.POWER_OFF_HOLD_MS
        if completed and not getattr(self, '_power_hold_ready', False):
            self._event_buzzer_melody('POWER_HOLD_READY')
        self._clear_power_hold(restore=not completed, cancelled=not completed)
        if event.value >= self.POWER_OFF_HOLD_MS:
            if self.checkkey != self.PowerConfirm:
                self._open_power_hold_popup()
            self.lcd.update()
            return True
        if event.value >= self.SHORT_PRESS_MS or wake_only:
            self.lcd.update()
            return True  # An aborted hold is never a normal selection.
        self._process_input(InputEvent('press', 1, event.epoch, event.ui_epoch))
        return True

    def _power_hold_tick(self):
        started = getattr(self, '_power_hold_started', None)
        if started is None:
            return False
        # The hold animation otherwise bypasses normal state presentation.
        current = self.pd.subscription.snapshot()['status'].get('print_stats', {})
        if current.get('state') in ('printing', 'paused', 'pausing'):
            self._clear_power_hold(restore=False)
            self._update_ui_state()
            self.Goto_PrintProcess()
            self.lcd.update()
            return True
        deadline = getattr(self, '_remote_power_hold_deadline', None)
        if deadline is not None and time.monotonic() >= deadline:
            # Missing browser release/network loss cancels rather than powers off.
            self._clear_power_hold()
            self.lcd.update()
            return False
        if self._ui_lifecycle()['epoch'] != self._power_hold_epoch:
            self._clear_power_hold()
            self.lcd.update()
            return False
        elapsed = round((time.monotonic() - started) * 1000)
        if elapsed < self.SHORT_PRESS_MS or self.checkkey == self.PowerConfirm:
            return True
        first_step = not self._power_hold_visible
        dirty = first_step
        cue = 'POWER_HOLD_START' if first_step else None
        if not self._power_hold_visible:
            self._power_hold_visible = True
            show_icon(self.lcd, self.ICON, ICON_POWER_HOLD_PANEL, 28, 160)
            self.lcd.draw_text(False, False, self.lcd.font8x16,
                self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window, 80, 178, 'Hold for power')
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 44, 214, 227, 221)
        progress = min(1, max(0, (elapsed - self.SHORT_PRESS_MS)
                       / (self.POWER_OFF_HOLD_MS - self.SHORT_PRESS_MS)))
        pixels = round(progress * 184)
        if pixels > self._power_hold_pixels:
            if not first_step:
                cue = 'POWER_HOLD_STEP'
            dirty = True
            self.lcd.draw_rectangle(1, 0x063B, 44 + self._power_hold_pixels,
                                    214, 43 + pixels, 221)
            self._power_hold_pixels = pixels
        if progress == 1 and not self._power_hold_ready:
            dirty = True
            self._power_hold_ready = True
            cue = 'POWER_HOLD_READY'
            self.lcd.draw_text(False, False, self.lcd.font8x16,
                self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                56, 236, 'Release to continue')
        if cue is not None:
            self._event_buzzer_melody(cue)
        if dirty:
            self.lcd.update()
        return True

    def _power_block_reason(self):
        reason = self.pd.power_off_block_reason()
        if reason:
            return reason
        if self.pd.status in ('printing', 'paused', 'pausing'):
            return 'Print is active'
        if getattr(self, '_pending_start', None) or getattr(self, '_action_feedback', None) or getattr(self, '_quiet_edits', None):
            return 'Operation is running'
        return None

    def _power_print_takeover(self):
        """Drop stale power controls without restoring the now-unsafe origin."""
        self._power_origin = None
        self._power_focus = False
        self._power_hold_popup = False
        self._power_confirm_yes = False
        self._power_blocked = None
        self._power_shutdown_requested = False
        self.Goto_PrintProcess()
        self.lcd.update()

    def _open_power_hold_popup(self):
        self._update_ui_state()
        if self.pd.status in ('printing', 'paused', 'pausing'):
            self._power_print_takeover()
            return
        self._power_origin = self.checkkey
        self._power_origin_epoch = self.pd.state.epoch
        self._power_confirm_yes = False
        self._power_focus = False
        self._power_hold_popup = True
        self._power_shutdown_requested = False
        self._power_blocked = self._power_block_reason()
        self.checkkey = self.PowerConfirm
        self._draw_power_confirmation()

    def _power_popup_tick(self):
        if not getattr(self, '_power_hold_popup', False) or self.checkkey != self.PowerConfirm:
            return False
        self._update_ui_state()
        for name in ('bed_mesh','screws_tilt','probe_wizard','mmu_session'):
            getattr(self.pd,name).update()
        self._focus_tick_quiet()
        if self.pd.status in ('printing', 'paused', 'pausing'):
            self._power_print_takeover()
            return True
        if self.pd.state.epoch != self._power_origin_epoch:
            self._power_origin = self.MainMenu
            self._restore_power_origin()
            self.lcd.update()
            return True
        if getattr(self, '_power_shutdown_requested', False):
            future = getattr(self, '_power_off_future', None)
            if isinstance(future, Future) and future.done() and (future.cancelled() or future.exception()):
                self._power_shutdown_requested = False
                self._power_confirm_yes = False
                self._power_blocked = 'Power off failed'
                self._draw_power_confirmation()
                self.lcd.update()
            return True
        reason = self._power_block_reason()
        if reason != self._power_blocked:
            self._power_blocked = reason
            self._draw_power_confirmation()
            self.lcd.update()
        return True  # Do not let background screen redraws overwrite the popup.

    def _restore_power_editor(self):
        screen = self.checkkey
        if screen == self.TuneEdit:
            self._focus_edit_draw()
            return True
        if screen == self.PrintErrorDetails:
            self._focus_error_draw()
            return True
        if screen in (self.PLAPreheat, self.ABSPreheat):
            self._draw_capability_menu('preheat', self.select_PLA,
                                      profile=getattr(self, '_active_preset', 0))
            return True
        if screen == self.MotionValue:
            self.Draw_Motion_Menu()
            return True
        if screen == self.CaseLightBrightness:
            self.Draw_Case_Light_Menu()
            self._invalidate_list_row(self._menu_row(2))
            self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                self.lcd.Color_White, self.lcd.Select_Color, 3, 208, self.MBASE(self._menu_row(2)),
                self._case_light_brightness_target)
            return True
        axes = {self.Move_X: ('Move_X_scale', 1), self.Move_Y: ('Move_Y_scale', 2),
                self.Move_Z: ('Move_Z_scale', 3), self.Extruder: ('Move_E_scale', 4)}
        if screen in axes:
            self.Draw_Move_Menu()
            attr, logical = axes[screen]
            row = self._menu_row(logical)
            self._invalidate_list_row(row)
            value = getattr(self.pd.HMI_ValueStruct, attr)
            if screen == self.Extruder:
                self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16, self.lcd.Select_Color,
                                                       3, 1, 216, self.MBASE(row), value)
            else:
                self.lcd.draw_scaled_float_text(True, True, 0, self.lcd.font8x16,
                    self.lcd.Color_White, self.lcd.Select_Color, 3, 1, 216, self.MBASE(row), value)
            return True
        if screen == self.Homeoffset:
            prepare = self.pd.HMI_ValueStruct.show_mode == -4
            (self.Draw_Prepare_Menu if prepare else self.Draw_Tune_Menu)()
            row = self._menu_row(self.PREPARE_CASE_ZOFF if prepare else self.TUNE_CASE_ZOFF)
            self._zoffset_edit_row = self._invalidate_list_row(row)
            self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16, self.lcd.Select_Color,
                                                   2, 2, 202, self.MBASE(row), self._zoffset_target)
            return True
        if screen in (self.PrintSpeed, self.ETemp, self.BedTemp, self.FanSpeed):
            mode = self.pd.HMI_ValueStruct.show_mode
            if screen == self.PrintSpeed or mode not in (-1, -2):
                self.Draw_Tune_Menu()
            elif mode == -1:
                self.Draw_Temperature_Menu()
            else:
                self._draw_capability_menu('preheat', self.select_PLA,
                    self.index_preset, profile=getattr(self, '_active_preset', 0))
            attr, case = {self.PrintSpeed: ('print_speed', self.TUNE_CASE_SPEED),
                          self.ETemp: ('E_Temp', self.TUNE_CASE_TEMP),
                          self.BedTemp: ('Bed_Temp', self.TUNE_CASE_BED),
                          self.FanSpeed: ('Fan_speed', self.TUNE_CASE_FAN)}[screen]
            if mode == -1 and screen != self.PrintSpeed:
                case = {self.ETemp: self.TEMP_CASE_TEMP, self.BedTemp: self.TEMP_CASE_BED,
                        self.FanSpeed: self.TEMP_CASE_FAN}[screen]
            elif mode == -2 and screen != self.PrintSpeed:
                case = {self.ETemp: self.PREHEAT_CASE_TEMP, self.BedTemp: self.PREHEAT_CASE_BED}[screen]
            render = getattr(self, '_list_render', None)
            row = case - (render['start'] if render is not None else 0)
            self._invalidate_list_row(row)
            if screen != self.PrintSpeed:
                self._thermal_edit_row = row
            self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                self.lcd.Color_White, self.lcd.Select_Color, 3, 216, self.MBASE(row),
                getattr(self.pd.HMI_ValueStruct, attr))
            return True
        return False
