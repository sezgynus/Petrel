"""Existing PetrelDisplay methods grouped by responsibility."""
from petrel.ui.selection import select_t
import time
import logging
from petrel.ui.events import InputEvent


class DisplayInputMixin:
    def _enqueue_input(self, kind, value, accelerated_value=0, rate=0.0):
        feedback = getattr(self, '_action_feedback', None)
        recovering = getattr(self, 'checkkey', None) == self.RecoveryScreen
        if (self.pd is None or self._closed or not getattr(self, '_uart_online', True)
                or (not recovering and feedback is not None
                    and not (feedback.phase == 'error' and kind == 'press'))):
            return False
        snapshot = self._ui_lifecycle()
        if (snapshot['state'] != 'ready'
                and getattr(self, 'checkkey', None) != self.MMUMenu
                and not (recovering and kind in ('rotate', 'press'))):
            return False
        accepted = self._loop.post(InputEvent(
            kind, value, snapshot['epoch'], getattr(self, '_uart_epoch', 0),
            accelerated_value, rate))
        if not accepted:
            logging.warning('LCD input queue full or closed; input discarded')
        return accepted

    def _remote_input(self, kind, value):
        # HTTP threads only enqueue epoch-bound events. The UI owner drives
        # the existing guarded hold/release shortcut, never direct shutdown.
        if kind == 'press' and value == 1:
            return self._enqueue_input('press', 1)
        if kind == 'rotate' and type(value) is int and 0 < abs(value) <= 6:
            return self._enqueue_input('rotate', value, value)
        if kind == 'hold_start' and value == 1:
            return self._enqueue_input('remote_button_down', 1)
        if kind == 'hold_end' and type(value) is int and 0 <= value <= 10000:
            return self._enqueue_input('remote_button_release', value)
        if kind == 'hold_cancel' and value == 1:
            return self._enqueue_input('remote_button_cancel', 1)
        return False

    def encoder_has_data(self, value):
        # GPIO thread: capture rotation only; never draw or execute UI handlers.
        with self._input_lock:
            delta = value - self._producer_value
            self._producer_value = value
            if not delta:
                return
            now = time.monotonic()
            multiplier = 1
            rate = 0.0
            last_encoder_time = getattr(self, '_last_encoder_time', None)
            if last_encoder_time is not None:
                elapsed = now - last_encoder_time
                if elapsed > 0:
                    rate = abs(delta) / elapsed
                    if rate > self.ENCODER_ACCEL_START_STEPS_PER_SEC:
                        span = (self.ENCODER_ACCEL_FULL_STEPS_PER_SEC
                                - self.ENCODER_ACCEL_START_STEPS_PER_SEC)
                        normalized = min(1.0, (rate - self.ENCODER_ACCEL_START_STEPS_PER_SEC) / span)
                        multiplier = max(1, round(
                            1 + (self.ENCODER_FAST_MULTIPLIER - 1)
                            * normalized ** self.ENCODER_ACCEL_EXPONENT))
            self._last_encoder_time = now
            self._enqueue_input('rotate', delta, delta * multiplier, rate)

    def _button_pressed(self):
        self._maintenance_button_presses = getattr(self,'_maintenance_button_presses',0)+1
        # A zero hold time makes the press edge itself request printer power.
        if getattr(self, 'power_on_hold_ms', 2000) == 0 and getattr(self, '_relay_status', None) != 'on':
            self._request_power_on()
        self._power_button_down()

    def _request_power_on(self):
        # Power control must remain available while Klipper and/or the LCD UART are offline.
        if self.pd is None or self._closed:
            return
        if not self._loop.post(InputEvent('power_on', 1, 0, 0)):
            logging.warning('LCD input queue full or closed; power-on request discarded')

    def _button_held(self):
        if (getattr(self, 'power_on_hold_ms', 2000) > 0
                and not getattr(self, '_button_can_power_off', False)):
            self._request_power_on()

    def _sync_input_state(self, event):
        previous_epoch = self.pd.state.epoch
        self._update_ui_state()
        if self._mmu_power_popup_stale():
            self._restore_power_origin()
            self.lcd.update()
            return False
        if getattr(self, 'checkkey', None) == self.MMUMenu and not self.pd.state.ready:
            self._poll_mmu()
            return True  # Offline MMU navigation remains read-only.
        if (self.pd.connection_error or not self.pd.state.ready
                or self.pd.state.epoch != event.epoch):
            return False
        changed = self._configure_menus()
        if previous_epoch != self.pd.state.epoch or changed:
            # Input was captured against an older menu/capability model.
            for name in self.SELECTIONS:
                getattr(self, name).reset()
            self.index_prepare = self.index_tune = self.MROWS
            self._offline = False
            self.HMI_StartFrame(False)
            self.lcd.update()
            return False
        if self._active_print_requires_focus():
            # User input can race the normal 500 ms state update.
            self._present_print_state()
            self.lcd.update()
            return False
        return True

    def _encoder_acceleration_cap(self):
        screen = getattr(self, 'checkkey', None)
        if screen in (self.Move_X, self.Move_Y, self.Move_Z, self.Extruder):
            return 250
        if screen == self.MotionValue:
            return 100
        if screen in (self.ETemp, self.BedTemp):
            return 10
        if screen in (self.PrintSpeed, self.FanSpeed):
            return 5
        if screen == self.Homeoffset:
            return 10
        return 1

    def _process_input(self,event):
        self._trace_maintenance_ui('input_before',event)
        try:
            return self._process_input_untraced(event)
        except Exception as error:
            trace = getattr(self.pd,'maintenance_test_trace',None)
            if trace is not None and trace.active:
                trace.emit('ui_handler_error',{'type':type(error).__name__})
            raise
        finally:
            self._cap_flash_interval()
            self._trace_maintenance_ui('input_after',event)

    def _queue_nfc_ui_event(self, kind):
        # Backend/Core callbacks never draw or enter the DWIN UI thread.
        loop = getattr(self, '_loop', None)
        if loop is not None and not getattr(self, '_closed', False):
            loop.post_coalesced(InputEvent(kind, 0, 0, getattr(self, '_uart_epoch', 0)))
        return False

    def _process_input_untraced(self, event):
        if event.kind.startswith('melody_'):
            name = event.kind[7:]
            if name in ('PRINT_DONE', 'PAUSE', 'RESUME', 'ERROR', 'HEATING_DONE',
                        'COOLING_DONE', 'HOMING', 'PROBE_SUCCESS', 'PROBE_FAIL', 'LAYER_CHANGE', 'FILAMENT_OUT'):
                live = self.pd.subscription.lifecycle()
                valid = (event.epoch == live['epoch'] or
                         (name == 'ERROR' and live['state'] != 'ready'
                          and event.epoch + 1 == live['epoch']))
                if valid:
                    self._event_buzzer_melody(name)
            return
        if event.kind in ('nfc_gate_lookup', 'nfc_gate_verify'):
            if not self._closed:
                (self._nfc_gate_result if event.kind == 'nfc_gate_lookup'
                 else self._nfc_gate_verify)()
            return
        if event.kind == 'nfc_spool_ready':
            if not self._closed:
                self._spool_result_event()
            return
        if event.kind == 'nfc_emg_capture':
            if not self._closed:
                self._rfid_assignment_event()
            return
        if event.kind in ('nfc_share_done', 'nfc_share_failed', 'nfc_share_cancelled'):
            if (getattr(self, '_nfc_share_popup', None)
                    and self.pd.subscription.snapshot()['status']['print_stats']['state']
                    in ('printing', 'paused', 'pausing')):
                self._cancel_nfc_share_popup(redraw=False)
                return
            if getattr(self, '_nfc_share_popup', None):
                if event.kind in ('nfc_share_done', 'nfc_share_cancelled'):
                    if event.kind == 'nfc_share_done':
                        self._event_buzzer_melody('NFC_SHARE_DONE')
                    self._finish_nfc_share_popup()
                else:
                    self._nfc_share_popup = 'failed'
                    if self._uart_online:
                        self._draw_nfc_share_popup()
                        self.lcd.update()
            return
        if event.kind in ('nfc_card', 'nfc_status', 'nfc_capabilities'):
            if not self._closed:
                previous_nfc = self.pd.system_info.get('nfc')
                self.pd.sync_nfc_event()
                component = self._nfc_share_component()
                availability_changed = component.sync()
                if self._uart_online and self.checkkey == self.RFIDMenu:
                    self.Draw_RFID_Menu(full=False)
                    self.lcd.update()
                elif (self._uart_online and self.checkkey == self.Info
                      and not getattr(self, '_nfc_share_popup', None)
                      and (availability_changed or previous_nfc != self.pd.system_info.get('nfc'))):
                    self.Draw_Info_Menu()
                    self.lcd.update()
            return
        if event.kind == 'power_on':
            if not self._closed:
                self.pd.power_on_if_off()
            return
        if getattr(self, '_boot_active', False):
            return
        if (not getattr(self, '_uart_online', True)
                or event.ui_epoch != getattr(self, '_uart_epoch', 0)):
            return
        if (getattr(self, '_nfc_gate_popup', None)
                and self.checkkey == self.NFCGateMenu
                and event.kind in ('press', 'rotate')):
            self._nfc_gate_input(event)
            return
        # An active NFC target-mode session must remain cancellable even if
        # Moonraker/Klipper becomes unavailable during phone interaction.
        if getattr(self, '_nfc_share_popup', None) and event.kind in ('press', 'rotate'):
            if event.kind == 'press':
                self._cancel_nfc_share_popup()
            return
        if (getattr(self, 'checkkey', None) == self.RecoveryScreen
                and self.pd.connection_error and not self._closed):
            self._recovery_input(event)
            return
        snapshot = self._ui_lifecycle()
        if ((snapshot['state'] != 'ready' and getattr(self, 'checkkey', None) != self.MMUMenu) or snapshot['epoch'] != event.epoch
                or self._closed):
            if event.kind in ('button_release', 'remote_button_release', 'remote_button_cancel') and getattr(self, '_power_hold_started', None) is not None:
                self._clear_power_hold()
                self.lcd.update()
            return
        if event.kind == 'case_light_status':
            self._poll_case_light_state()
            return
        if event.kind == 'case_light_flush':
            self._poll_case_light_live()
            return
        if event.kind == 'live_jog_flush':
            self._flush_live_jog()
            return
        if self._power_button_input(event):
            return
        if event.kind == 'rotate' and getattr(self, '_power_hold_started', None) is not None:
            return
        if event.kind == 'rotate':
            direction = self.ENCODER_DIFF_CCW if event.value > 0 else self.ENCODER_DIFF_CW
            count = abs(event.value)
        elif event.kind == 'press':
            direction, count = self.ENCODER_DIFF_ENTER, 1
        else:
            return
        if self._display_activity():
            return
        if not self._sync_input_state(event):
            return
        self._buzzer_feedback(event.kind)
        self._encoder_jog_rate = event.rate if event.kind == 'rotate' else 0.0
        acceleration_cap = self._encoder_acceleration_cap() if event.kind == 'rotate' else 1
        if event.kind == 'rotate' and getattr(self, 'checkkey', None) == self.CaseLightBrightness:
            # Apply coalesced physical detents once, without acceleration.
            self._encoder_move_value = count
            count = 1
        elif acceleration_cap > 1:
            count = 1
            raw_count = max(1, abs(event.value))
            accelerated_count = abs(event.accelerated_value or event.value)
            effective_multiplier = max(1, accelerated_count // raw_count)
            self._encoder_move_value = raw_count * min(acceleration_cap, effective_multiplier)
        else:
            self._encoder_move_value = 1
        self._rotation_steps = abs(event.value) if event.kind == 'rotate' else 1
        self._menu_batch_steps = self._rotation_steps
        if event.kind == 'rotate':
            if acceleration_cap == 1:
                self._encoder_move_value = self._rotation_steps
            count = 1  # One bounded handler invocation per physical input batch.
        for name in self.SELECTIONS:
            selection = getattr(self, name, None)
            if isinstance(selection, select_t):
                selection.batch_steps = self._rotation_steps
        lcd = getattr(self, 'lcd', None)
        if lcd is not None:
            lcd._defer_updates = True
        try:
            for _ in range(count):
                current = self._ui_lifecycle()
                if ((current['state'] != 'ready' and getattr(self, 'checkkey', None) != self.MMUMenu)
                        or current['epoch'] != event.epoch):
                    break
                self._encoder_event = direction
                self._dispatch_input()
                if getattr(self, '_action_feedback', None):
                    self._poll_action()
                    break
        except OSError:
            if self.lcd is not None and getattr(self.lcd, '_closed', False):
                self._uart_failed()
            else:
                raise
        finally:
            self._encoder_event = self.ENCODER_DIFF_NO
            self._encoder_move_value = 1
            self._menu_batch_steps = self._rotation_steps = 1
            for name in self.SELECTIONS:
                selection = getattr(self, name, None)
                if isinstance(selection, select_t): selection.batch_steps = 1
            if (lcd is not None and self.lcd is lcd
                    and not getattr(lcd, '_closed', False)):
                lcd._defer_updates = False
                lcd.update()
            self._sync_case_light_tracking()

    def _dispatch_input(self):
        if self.checkkey == self.PowerConfirm and getattr(self, '_power_hold_popup', False):
            self._handle_power_navigation()
            return
        editors = (self.Move_X, self.Move_Y, self.Move_Z, self.Extruder,
                   self.PrintSpeed, self.ETemp, self.BedTemp, self.FanSpeed,
                   self.Homeoffset, self.CaseLightBrightness)
        cached = getattr(self, '_list_render', None)
        if cached and self.checkkey in editors:
            cached['values'].pop(cached['selection'], None)
        feedback = getattr(self, '_action_feedback', None)
        if feedback is not None:
            if feedback.phase == 'error' and self.get_encoder_state() == self.ENCODER_DIFF_ENTER:
                self._action_feedback = None
                self._restore_action_screen()
            return
        if getattr(self, '_pending_start', None):
            return
        if getattr(self, '_start_error_visible', False):
            if self.get_encoder_state() == self.ENCODER_DIFF_ENTER:
                self._start_error_visible = False
                self.Goto_MainMenu()
                self.lcd.update()
            return
        if getattr(self, '_print_error_visible', False):
            if self.get_encoder_state() == self.ENCODER_DIFF_ENTER:
                self._acknowledged_terminal = self._terminal_key()
                self._print_error_visible = False
                self.Goto_MainMenu()
                self.lcd.update()
            return
        if self._handle_power_navigation():
            return
        if self.checkkey == self.MainMenu:
            self.HMI_MainMenu()
        elif self.checkkey == self.SelectFile:
            self.HMI_SelectFile()
        elif self.checkkey == self.Prepare:
            self.HMI_Prepare()
        elif self.checkkey == self.Control:
            self.HMI_Control()
        elif self.checkkey == self.PrintProcess:
            self.HMI_Printing()
        elif self.checkkey == self.Print_window:
            self.HMI_PauseOrStop()
        elif self.checkkey == self.AxisMove:
            self.HMI_AxisMove()
        elif self.checkkey == self.TemperatureID:
            self.HMI_Temperature()
        elif self.checkkey == self.Motion:
            self.HMI_Motion()
        elif self.checkkey in (self.ScrewsTiltMenu, self.ScrewsTiltResult):
            self.HMI_Screws_Tilt()
        elif self.checkkey == self.FilePreview:
            self.HMI_File_Preview()
        elif self.checkkey == self.MMUMenu:
            self.HMI_MMU_Menu()
        elif self.checkkey == self.BedMeshMenu:
            self.HMI_Bed_Mesh_Menu()
        elif self.checkkey == self.BedMeshScreen:
            self.HMI_Bed_Mesh()
        elif self.checkkey == self.MeshProfiles:
            self.HMI_Mesh_Profiles()
        elif self.checkkey == self.ProbeWizardID:
            self.HMI_Probe_Wizard()
        elif self.checkkey == self.MotionValue:
            self.HMI_MotionValue()
        elif self.checkkey == self.MaintenanceMenu:
            self.HMI_Maintenance_Menu()
        elif self.checkkey == self.NFCSettingsMenu:
            self.HMI_NFC_Settings_Menu()
        elif self.checkkey == self.NFCChoiceMenu:
            self.HMI_NFC_Choice_Menu()
        elif self.checkkey == self.EventSoundsMenu:
            self.HMI_Event_Sounds_Menu()
        elif self.checkkey == self.DisplayMenu:
            self.HMI_Display_Menu()
        elif self.checkkey == self.RFIDMenu:
            self.HMI_RFID()
        elif self.checkkey == self.Info:
            self.HMI_Info()
        elif self.checkkey == self.Tune:
            self.HMI_Tune()
        elif self.checkkey == self.TuneEdit:
            self._focus_edit_input()
        elif self.checkkey == self.PrintErrorDetails:
            self._focus_error_input()
        elif self.checkkey == self.PLAPreheat:
            self.HMI_PLAPreheatSetting()
        elif self.checkkey == self.ABSPreheat:
            self.HMI_ABSPreheatSetting()
        elif self.checkkey == self.Move_X:
            self.HMI_Move_X()
        elif self.checkkey == self.Move_Y:
            self.HMI_Move_Y()
        elif self.checkkey == self.Move_Z:
            self.HMI_Move_Z()
        elif self.checkkey == self.Extruder:
            self.HMI_Move_E()
        elif self.checkkey == self.ETemp:
            self.HMI_ETemp()
        elif self.checkkey == self.Homeoffset:
            self.HMI_Zoffset()
        elif self.checkkey == self.BedTemp:
            self.HMI_BedTemp()
        elif self.checkkey == self.FanSpeed:
            self.HMI_FanSpeed()
        elif self.checkkey == self.PrintSpeed:
            self.HMI_PrintSpeed()
        elif self.checkkey == self.CaseLight:
            self.HMI_Case_Light()
        elif self.checkkey == self.CaseLightBrightness:
            self.HMI_Case_Light_Brightness()

    def get_encoder_state(self):
        # Input is an immutable queued event, not a sample of current GPIO levels.
        return self._encoder_event
