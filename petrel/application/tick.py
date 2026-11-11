"""Existing PetrelDisplay methods grouped by responsibility."""
from petrel.ui.theme import show_icon as show_theme_icon
import copy
import time
import logging


class DisplayTickMixin:
    def _update_ui_state(self):
        if getattr(self, '_tick_active', False) and self._tick_state_update is not None:
            return self._tick_state_update
        changed = self.pd.update_variable()
        self._sync_file_lifecycle()
        if getattr(self, '_tick_active', False):
            self._tick_state_update = changed
        return changed

    def _cap_flash_interval(self):
        # Apply after screen-specific intervals and immediately after input:
        # a settings RPC must not advance at the 500ms dashboard cadence.
        if (getattr(self, '_uart_online', False)
                and getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True
                and self.lcd.flash_busy() and hasattr(self, '_loop')):
            self._loop.cap_interval(.05)

    def _ui_tick(self):
        self._tick_active = True
        self._tick_state_update = None
        try:
            self._ui_tick_body()
        finally:
            self._tick_active = False
            self._cap_flash_interval()
            if any(getattr(getattr(self.pd, name, None), 'pending', False) is True
                   for name in ('maintenance_pulse', 'maintenance_reader')):
                if hasattr(self, '_loop'):
                    self._loop.cap_interval(.1)

    def _ui_tick_body(self):
        if (getattr(self, '_rfid_assignment', None) is not None
                and not self._rfid_context_active()):
            self._rfid_cancel_assignment()
        # Operation deadlines must not depend on the visible screen or LCD.
        self._maintenance_advanced_this_tick = False
        if any(getattr(getattr(self.pd, name, None), 'pending', False) is True
               for name in ('maintenance_pulse', 'maintenance_reader')):
            self._update_ui_state()
            self._advance_maintenance_operations()
            self._maintenance_advanced_this_tick = True
        self._poll_panel_power()
        self._sync_case_light_tracking()
        if not self._uart_online:
            # Keep status current while the panel is disconnected.
            self._update_ui_state()
            self.pd.bed_mesh.update()
            self.pd.mmu_session.update()
            self._ensure_uart()
            return
        try:
            now = time.monotonic()
            flash_active = False
            if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                self.lcd.poll_flash_tasks()
                self._poll_panel_flash()
                flash_active = self.lcd.flash_busy()
                if flash_active:
                    # Data Flash may be busy programming a repeated value.
                    # Never treat an unanswered 500ms liveness ping during a
                    # 3s Flash write as evidence that the LCD disappeared.
                    # Postpone the *next* ping until after the write settles.
                    self._next_uart_probe = now + 2.0
                    if hasattr(self, '_loop'):
                        self._loop.set_interval(.05)
            if self._power_hold_tick():
                return
            incremental_probe = (getattr(self.lcd,
                                          'SUPPORTS_NONBLOCKING_LIVENESS', None) is True)
            if not flash_active and now >= getattr(self, '_next_uart_probe', 0):
                self._next_uart_probe = now + 2.0
                if incremental_probe:
                    self.lcd.begin_liveness_probe(timeout=0.5)
                else:
                    result = self.lcd.handshake(timeout=0.5)
                    if result:
                        self._uart_probe_failures = 0
                    else:
                        self._uart_probe_failures = getattr(self, '_uart_probe_failures', 0) + 1
            if incremental_probe:
                result = self.lcd.poll_liveness_probe()
                if not flash_active:
                    if result is True:
                        self._uart_probe_failures = 0
                    elif result is False:
                        self._uart_probe_failures = getattr(self, '_uart_probe_failures', 0) + 1
            if getattr(self, '_uart_probe_failures', 0):
                if self._uart_probe_failures >= 2:
                    logging.warning('LCD liveness lost; reconnecting')
                    self._uart_failed()
                    return
            if self._power_popup_tick():
                return
            if self._nfc_gate_tick():
                return
            if getattr(self, '_boot_active', False):
                self._poll_boot()
                return
            if (getattr(self, 'checkkey', None) == self.MMUMenu
                    and getattr(self, '_mmu_page', None) == 'home'):
                view = getattr(self, '_mmu_filament_view', None)
                state = getattr(self, '_mmu_animation_state', None)
                animating = bool(view is not None and state is not None
                                 and view.animating(state, now))
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05 if animating else .5)
                if now < getattr(self, '_mmu_status_at', 0):
                    if animating:
                        self._mmu_animation_tick()
                    return
                self._mmu_status_at = now + .5
            elif getattr(self, 'checkkey', None) == self.RFIDMenu:
                # RFID renders only on NFC Core events; no 50ms poll or refresh.
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.5)
            elif getattr(self, 'checkkey', None) == self.FilePreview:
                if not getattr(self, '_pending_start', None) and not getattr(self, '_start_error_visible', False):
                    self._poll_file_preview()
                if not getattr(self, '_pending_start', None) and hasattr(self, '_loop'):
                    active = (not getattr(self, '_start_error_visible', False)
                              and self._preview_epoch == self.pd.state.epoch
                              and self._thumbnail_cache.has_foreground_work(self._preview_cache_key))
                    self._loop.set_interval(.02 if active else .5)
                if time.monotonic() < getattr(self, '_preview_status_at', 0):
                    return
                self._preview_status_at = time.monotonic() + .5
            elif getattr(self, 'checkkey', None) == self.SelectFile:
                self._poll_thumbnail_preload()
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.02 if self._thumbnail_cache.has_work() else .5)
                if time.monotonic() < getattr(self, '_file_status_at', 0):
                    return
                self._file_status_at = time.monotonic() + .5
            elif hasattr(self, '_loop'):
                blink = bool(getattr(self, '_quiet_blinks', {}))
                loading = self.checkkey == self.PrintProcess and hasattr(self, '_thumbnail_cache') and self._thumbnail_cache.has_work()
                self._loop.set_interval(.1 if blink else (.05 if loading else .5))
            if (getattr(self, 'checkkey', None) in (self.NFCSettingsMenu, self.NFCChoiceMenu)
                    and (self.checkkey == self.NFCSettingsMenu
                         or getattr(self, '_nfc_choice_field', None) == 'port')
                    and getattr(self, '_nfc_port_future', None) is not None):
                if hasattr(self, '_loop'):
                    self._loop.cap_interval(.1)
                self._nfc_poll_port_choices()
            if (getattr(self, 'checkkey', None) == self.NFCSettingsMenu
                    and getattr(self, '_nfc_test_future', None) is not None):
                if hasattr(self, '_loop'):
                    self._loop.cap_interval(.1)
                self._nfc_poll_test_connection()
            if getattr(self, '_mesh_pending_points', None) is not None:
                if self.checkkey == self.BedMeshScreen:
                    if hasattr(self, '_loop'):
                        self._loop.set_interval(.02)
                    self._advance_mesh_render()
                else:
                    self._mesh_pending_points = None
            if incremental_probe and getattr(self.lcd, '_liveness_deadline', None) is not None:
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
            self._display_idle_tick()
            if self._draw_header_clock():
                self.lcd.update()
            self.EachMomentUpdate()
        except OSError:
            if self.lcd is not None and getattr(self.lcd, '_closed', False):
                self._uart_failed()
            else:
                raise

    def _each_moment_update_untraced(self):
        wifi_changed = self.pd.refresh_wifi_status()  # Worker only; also invalidate visible Info rows.
        self._poll_case_light_live()
        self._sync_case_light_tracking()
        self._poll_case_light_state()
        # variable update
        update = self._update_ui_state()
        self._poll_maintenance_ui()
        self._focus_tick_quiet()
        if self.pd.connection_error:
            # Invalidate active operation sessions before the recovery screen
            # takes over; do not leave mesh/probe sessions running invisibly.
            self._poll_screws_tilt()
            self._poll_bed_mesh()
            self.pd.probe_wizard.update()
            if self._poll_recovery_ui():
                return
        else:
            self._poll_recovery_ui()
        if not self.pd.connection_error and self.checkkey not in (self.SelectFile, self.FilePreview):
            self.pd.prefetch_files()
        if not self.pd.connection_error and self._configure_menus():
            for name in self.SELECTIONS:
                getattr(self, name).reset()
            self.index_prepare = self.index_tune = self.index_control = self.MROWS
            self._offline = True
        self._poll_mmu()
        if self._active_print_requires_focus():
            # The MMU screen used to consume the print state edge without
            # changing screens, leaving idle menus reachable during a job.
            self._present_print_state()
        if self.checkkey == self.MMUMenu:
            self._offline = bool(self.pd.connection_error)
            if self.last_status != self.pd.status:
                self._present_print_state()
            return
        if self._poll_action():
            return
        self._poll_screws_tilt()
        self._poll_bed_mesh()
        self.pd.probe_wizard.update()
        if self.pd.connection_error and self.checkkey in (self.BedMeshScreen, self.MeshProfiles):
            self._offline = True
            return
        if self.pd.connection_error:
            if not self._offline:
                self._show_message('Moonraker unavailable')
            self._offline = True
            return
        self.pd.probe_wizard.update()
        info_update = False
        if self.checkkey == self.Info:
            info_update = self._software_updater().poll()
        if self.checkkey == self.Info:
            system_changed = self.pd.refresh_system_info()
            if (system_changed or wifi_changed) and not getattr(self, '_nfc_share_popup', None):
                self.Draw_Info_Menu()
                self.lcd.update()
            elif info_update:
                self._refresh_info_update_button()
        if self._poll_print_start() or getattr(self, '_start_error_visible', False):
            return
        if self.checkkey == self.SelectFile and (
                self.pd._files_loading or self.pd._directory_loading
                or self.pd.state.epoch != getattr(self, '_file_view_epoch', -1)
                or self.pd.state.file_revision != getattr(self, '_file_view_revision', -1)
                or self.pd.file_sort_revision != getattr(self, '_file_view_sort_revision', -1)):
            if self._refresh_file_snapshot():
                self.Redraw_SD_List()
        if self.pd.last_command_error:
            if self.pd.status in ('printing', 'paused', 'pausing'):
                # An asynchronous idle operation must never cover active Print.
                logging.warning('Printer command failed during print: %s',
                                self.pd.last_command_error)
                self.pd.last_command_error = None
            else:
                self._offline = True
                self._show_message('Command failed; check log')
                self.pd.last_command_error = None
                return
        if getattr(self, '_offline', False):
            self._offline = False
            self.HMI_StartFrame(False)
            if self.checkkey == self.FilePreview:
                self.Draw_File_Preview()
        # An active numeric move editor owns its value until confirmation
        # when live jog is disabled.  Only live-jog editors follow external
        # position updates while idle.
        if (update and getattr(self, '_live_jog', False)
                and getattr(self, '_live_jog_future', None) is None
                and getattr(self, '_live_jog_pending', None) is None):
            position = self.pd.state.status['gcode_move']['position']
            active_moves = {
                self.Move_X: ('Move_X_scale', 0, self.MBASE(1), False),
                self.Move_Y: ('Move_Y_scale', 1, self.MBASE(2), False),
                self.Move_Z: ('Move_Z_scale', 2, self.MBASE(3), False),
                self.Extruder: ('Move_E_scale', 3, self.MBASE(4), True),
            }
            active = active_moves.get(self.checkkey)
            if active is not None:
                attr, index, row, signed = active
                scale = position[index] * self.MINUNITMULT
                if getattr(self.pd.HMI_ValueStruct, attr) != scale:
                    setattr(self.pd.HMI_ValueStruct, attr, scale)
                    if attr == 'Move_E_scale':
                        self.pd.last_E_scale = scale
                    self._draw_axis_value(index, scale, row, self.lcd.Select_Color)
        if self.last_status != self.pd.status:
            self._present_print_state()
        if getattr(self, '_print_error_visible', False):
            return

        if self.checkkey == self.PrintProcess:
            self._focus_print_tick()
        elif self.checkkey == self.Tune:
            self._focus_tune_tick()
        elif self.checkkey in (self.TuneEdit, self.PrintErrorDetails):
            self._focus_tick_quiet()
        elif update and self.checkkey == self.TemperatureID:
            self.Draw_Temperature_Menu()
        elif update and self.checkkey == self.AxisMove:
            self.Draw_Move_Menu()
        elif update and self.checkkey == self.Motion:
            self.Draw_Motion_Menu()
        elif update and self.checkkey == self.BedMeshMenu:
            self.Draw_Bed_Mesh_Menu()
        elif self.checkkey == self.ProbeWizardID:
            self.Draw_Probe_Wizard()

        if self.pd.HMI_flag.home_flag:
            if self.pd.ishomed():
                self.CompletedHoming()

        if self.checkkey == self.MainMenu:
            mmu_state = self.pd.mmu
            if (mmu_state is None) != (getattr(self, '_drawn_mmu_state', None) is None):
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 4, 31, 268, 125)
                self._home_mmu_layout = None
                if mmu_state is None:
                    show_theme_icon(self.lcd, self.ICON, self.ICON_LOGO, 71, 48)
            if mmu_state is not None and mmu_state != getattr(self, '_drawn_mmu_state', None):
                self.Draw_MMU_Status()
            self._drawn_mmu_state = copy.deepcopy(mmu_state)
        self.Draw_Status_Area(True)
        self.lcd.update()

    def EachMomentUpdate(self):
        try:
            return self._each_moment_update_untraced()
        finally:
            # Includes recovery screens and all early returns.
            self._trace_maintenance_ui('tick')
