"""Existing display methods grouped by responsibility."""
from petrel.artwork.resources import ICON_ACCELERATION, ICON_CORNER_SPEED, ICON_CRUISE_RATIO, ICON_LIVE_JOG, ICON_VELOCITY
from petrel.ui.theme import show_icon as show_theme_icon
from petrel.ui.numbers import motion_text
from concurrent.futures import Future
from petrel.ui.events import InputEvent


class MotionViewMixin:
    def _live_jog_speed(self, axis):
        """Map handwheel rotation rate directly onto the configured axis velocity."""
        rate = max(0.0, float(getattr(self, '_encoder_jog_rate', 0.0)))
        toolhead = self.pd.state.status.get('toolhead', {})
        limit = float(toolhead.get('max_velocity', 1.0))
        if axis == 'Z':
            limit = min(limit, float(
                self.pd.state.settings.get('printer', {}).get('max_z_velocity', limit)))
        elif axis == 'E':
            hotend = self.pd.capabilities.active_hotend
            settings = self.pd.state.settings.get(hotend.name, {}) if hotend is not None else {}
            limit = float(settings.get('max_extrude_only_velocity', limit))
        # Full measured handwheel rate reaches the configured Klipper limit.
        normalized = min(1.0, rate / self.ENCODER_ACCEL_FULL_STEPS_PER_SEC)
        return max(1.0, limit * 60.0 * normalized)

    def _queue_live_jog(self, axis, distance, speed):
        pending = self._live_jog_pending
        if pending is None:
            self._live_jog_pending = [axis, distance, speed]
        elif pending[0] == axis and pending[1] * distance > 0:
            pending[1] += distance
            pending[2] = speed
        else:
            # A handwheel reversal or axis change supersedes queued motion.
            self._live_jog_pending = [axis, distance, speed]
        if self._live_jog_future is not None:
            return
        self._flush_live_jog()

    def _flush_live_jog(self):
        if self._live_jog_future is not None:
            done = self._live_jog_future
            if not done.done():
                return
            self._live_jog_future = None
            if done.cancelled() or done.exception() is not None:
                # Live jog is best-effort handwheel input.  A rejected segment
                # is dropped locally; the next encoder event is re-clamped
                # against fresh authoritative position.
                self._live_jog_pending = None
                return
        pending = self._live_jog_pending
        if pending is None or abs(pending[1]) < 1e-9:
            self._live_jog_pending = None
            return
        axis, distance, speed = pending
        self._live_jog_pending = None
        try:
            future = self.pd.moveRelative(axis, distance, speed)
        except ValueError:
            # Limits and transient state changes are silent for handwheel input.
            return
        if isinstance(future, Future):
            self._live_jog_future = future
            snapshot = self.pd.subscription.snapshot()
            future.add_done_callback(lambda _done: self._loop.post(InputEvent(
                'live_jog_flush', 0, snapshot['epoch'], getattr(self, '_uart_epoch', 0))))

    def HMI_AxisMove(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self.pd.PREVENT_COLD_EXTRUSION:
            # popup window resume
            if (self.pd.HMI_flag.ETempTooLow_flag):
                if (encoder_diffState == self.ENCODER_DIFF_ENTER):
                    self.pd.HMI_flag.ETempTooLow_flag = False
                    self.Draw_Move_Menu()
                    self.lcd.update()
                return
        # Avoid flicker by updating only the previous menu
        live_index = 4 + int(self.pd.HAS_HOTEND)
        if (encoder_diffState == self.ENCODER_DIFF_CW):
            if (self.select_axis.inc(live_index + 1)):
                self.Draw_Move_Menu()
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            if self.select_axis.dec():
                self.Draw_Move_Menu()
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if self.select_axis.now == 0:  # Back
                self.checkkey = self.Prepare
                self.select_prepare.set(1)
                self.index_prepare = self.MROWS
                self.Draw_Prepare_Menu()

            elif self.select_axis.now == 1:  # axis move
                self.checkkey = self.Move_X
                self._invalidate_list_row(self._menu_row(1))
                self.pd.HMI_ValueStruct.Move_X_scale = self.pd.state.status['gcode_move']['position'][0] * self.MINUNITMULT
                self._draw_axis_value(0,self.pd.HMI_ValueStruct.Move_X_scale,self.MBASE(self._menu_row(1)),self.lcd.Select_Color)
            elif self.select_axis.now == 2:  # Y axis move
                self.checkkey = self.Move_Y
                self._invalidate_list_row(self._menu_row(2))
                self.pd.HMI_ValueStruct.Move_Y_scale = self.pd.state.status['gcode_move']['position'][1] * self.MINUNITMULT
                self._draw_axis_value(1,self.pd.HMI_ValueStruct.Move_Y_scale,self.MBASE(self._menu_row(2)),self.lcd.Select_Color)
            elif self.select_axis.now == 3:  # Z axis move
                self.checkkey = self.Move_Z
                self._invalidate_list_row(self._menu_row(3))
                self.pd.HMI_ValueStruct.Move_Z_scale = self.pd.state.status['gcode_move']['position'][2] * self.MINUNITMULT
                self._draw_axis_value(2,self.pd.HMI_ValueStruct.Move_Z_scale,self.MBASE(self._menu_row(3)),self.lcd.Select_Color)
            elif self.select_axis.now == 4 and self.pd.HAS_HOTEND:  # Extruder
                # window tips
                if self.pd.PREVENT_COLD_EXTRUSION:
                    if not self.pd.state.status.get(self.pd.capabilities.active_hotend.name, {}).get('can_extrude', False):
                        self.pd.HMI_flag.ETempTooLow_flag = True
                        self.Popup_Window_ETempTooLow()
                        self.lcd.update()
                        return
                self.checkkey = self.Extruder
                self._invalidate_list_row(self._menu_row(4))
                self.pd.last_E_scale = self.pd.state.status['gcode_move']['position'][3] * self.MINUNITMULT
                self.pd.HMI_ValueStruct.Move_E_scale = self.pd.state.status['gcode_move']['position'][3] * self.MINUNITMULT
                self._draw_axis_value(3, self.pd.HMI_ValueStruct.Move_E_scale,
                                      self.MBASE(self._menu_row(4)), self.lcd.Select_Color)
            elif self.select_axis.now == live_index:
                self._live_jog = not getattr(self, '_live_jog', False)
                self.Draw_Move_Menu()
        self.lcd.update()

    def HMI_Move_X(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_X_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self._draw_axis_value(0,self.pd.HMI_ValueStruct.Move_X_scale,self.MBASE(self._menu_row(1)),self.lcd.Color_Bg_Black)
            if not getattr(self, '_live_jog', False):
                self._action("Jog X", lambda: self.pd.moveAbsolute('X', self.pd.HMI_ValueStruct.Move_X_scale / self.MINUNITMULT, 5000), silent=True)
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_X_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_X_scale -= self._encoder_move_value

        if self.pd.HMI_ValueStruct.Move_X_scale < (self.pd.X_MIN_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_X_scale = (self.pd.X_MIN_POS) * self.MINUNITMULT

        if self.pd.HMI_ValueStruct.Move_X_scale > (self.pd.X_MAX_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_X_scale = (self.pd.X_MAX_POS) * self.MINUNITMULT

        if getattr(self, '_live_jog', False) and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_X_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('X', applied, self._live_jog_speed('X'))
        self._draw_axis_value(0,self.pd.HMI_ValueStruct.Move_X_scale,self.MBASE(self._menu_row(1)),self.lcd.Select_Color)
        self.lcd.update()

    def HMI_Move_Y(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_Y_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self._draw_axis_value(1,self.pd.HMI_ValueStruct.Move_Y_scale,self.MBASE(self._menu_row(2)),self.lcd.Color_Bg_Black)

            if not self._live_jog:
                self._action("Jog Y", lambda: self.pd.moveAbsolute('Y', self.pd.HMI_ValueStruct.Move_Y_scale / self.MINUNITMULT, 5000), silent=True)
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_Y_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_Y_scale -= self._encoder_move_value

        if self.pd.HMI_ValueStruct.Move_Y_scale < (self.pd.Y_MIN_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Y_scale = (self.pd.Y_MIN_POS) * self.MINUNITMULT

        if self.pd.HMI_ValueStruct.Move_Y_scale > (self.pd.Y_MAX_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Y_scale = (self.pd.Y_MAX_POS) * self.MINUNITMULT

        if self._live_jog and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_Y_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('Y', applied, self._live_jog_speed('Y'))
        self._draw_axis_value(1,self.pd.HMI_ValueStruct.Move_Y_scale,self.MBASE(self._menu_row(2)),self.lcd.Select_Color)
        self.lcd.update()

    def HMI_Move_Z(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_Z_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self._draw_axis_value(2,self.pd.HMI_ValueStruct.Move_Z_scale,self.MBASE(self._menu_row(3)),self.lcd.Color_Bg_Black)
            if not self._live_jog:
                self._action("Jog Z", lambda: self.pd.moveAbsolute('Z', self.pd.HMI_ValueStruct.Move_Z_scale / self.MINUNITMULT, 600), silent=True)
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_Z_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_Z_scale -= self._encoder_move_value

        if self.pd.HMI_ValueStruct.Move_Z_scale < (self.pd.Z_MIN_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Z_scale = (self.pd.Z_MIN_POS) * self.MINUNITMULT

        if self.pd.HMI_ValueStruct.Move_Z_scale > (self.pd.Z_MAX_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Z_scale = (self.pd.Z_MAX_POS) * self.MINUNITMULT

        if self._live_jog and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_Z_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('Z', applied, self._live_jog_speed('Z'))
        self._draw_axis_value(2,self.pd.HMI_ValueStruct.Move_Z_scale,self.MBASE(self._menu_row(3)),self.lcd.Select_Color)
        self.lcd.update()

    def HMI_Move_E(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_E_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self._draw_axis_value(3, self.pd.HMI_ValueStruct.Move_E_scale,
                                  self.MBASE(self._menu_row(4)), self.lcd.Color_Bg_Black)
            if not self._live_jog:
                self._action("Jog E", lambda: self.pd.moveAbsolute('E', self.pd.HMI_ValueStruct.Move_E_scale / self.MINUNITMULT, 300), silent=True)
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_E_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_E_scale -= self._encoder_move_value

        if ((self.pd.HMI_ValueStruct.Move_E_scale - self.pd.last_E_scale) > (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT):
            self.pd.HMI_ValueStruct.Move_E_scale = self.pd.last_E_scale + (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT
        elif ((self.pd.last_E_scale - self.pd.HMI_ValueStruct.Move_E_scale) > (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT):
            self.pd.HMI_ValueStruct.Move_E_scale = self.pd.last_E_scale - (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT
        if self._live_jog and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_E_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('E', applied, self._live_jog_speed('E'))
        self._draw_axis_value(3, self.pd.HMI_ValueStruct.Move_E_scale,
                              self.MBASE(self._menu_row(4)), self.lcd.Select_Color)
        self.lcd.update()

    def HMI_Motion(self):
        event = self.get_encoder_state()
        settings = self.pd.motion_settings()
        if event == self.ENCODER_DIFF_CW:
            self.select_motion.inc(len(settings) + 1)
        elif event == self.ENCODER_DIFF_CCW:
            self.select_motion.dec()
        elif event == self.ENCODER_DIFF_ENTER:
            if self.select_motion.now == 0:
                self.checkkey = self.Control
                self.select_control.set(self.CONTROL_CASE_MOVE)
                self.Draw_Control_Menu()
                self.lcd.update()
                return
            if self.select_motion.now > len(settings):
                self.select_motion.reset()
            else:
                field, _, _, _, value = settings[self.select_motion.now - 1]
                self._motion_field, self._motion_target = field, value
                self.checkkey = self.MotionValue
        if event != self.ENCODER_DIFF_NO:
            self.Draw_Motion_Menu()
            self.lcd.update()

    def HMI_MotionValue(self):
        event = self.get_encoder_state()
        setting = next((item for item in self.pd.motion_settings()
                        if item[0] == self._motion_field), None)
        if setting is None:
            self.checkkey = self.Motion
            self.select_motion.reset()
        elif event == self.ENCODER_DIFF_ENTER:
            self._action("Motion limit", lambda: self.pd.set_motion_limit(self._motion_field, self._motion_target, idle_only=True), silent=True)
            self.checkkey = self.Motion
        elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            step = setting[3]
            change = step * self._encoder_move_value if event == self.ENCODER_DIFF_CW else -step * self._encoder_move_value
            previous = self._motion_target
            minimum = min(step, previous) if self._motion_field in ('max_velocity', 'max_accel') else 0
            self._motion_target = round(max(minimum, self._motion_target + change), 6)
            if self._motion_field == 'minimum_cruise_ratio':
                self._motion_target = min(max(.99, previous), self._motion_target)
        if event != self.ENCODER_DIFF_NO:
            self.Draw_Motion_Menu()
            self.lcd.update()

    def Draw_Motion_Menu(self):
        settings = self.pd.motion_settings()
        if self.select_motion.now > len(settings):
            self.select_motion.reset()
        entries = [('Back', self.ICON_Back, None, None)]
        for field, _, label, _, value in settings:
            editing = self.checkkey == self.MotionValue and self._motion_field == field
            if editing:
                value = self._motion_target
            text = motion_text(field,value)
            if len(text) > 9:
                text = '{:.3g}'.format(value)
            if len(text) > 9:
                text = '#' * 9
            painter = lambda row, text=text, editing=editing: self._draw_menu_value(
                text, self.MBASE(row),
                self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black,
                self.MENU_MOTION_CELLS)
            entries.append((label, {'max_velocity': ICON_VELOCITY,'max_accel': ICON_ACCELERATION,'square_corner_velocity': ICON_CORNER_SPEED,'minimum_cruise_ratio': ICON_CRUISE_RATIO}[field], (text, editing), painter))
        self._draw_list_menu('Motion (runtime)', entries, self.select_motion.now)

    def Draw_Move_Menu(self):
        position = self.pd.state.status['gcode_move']['position']
        entries = [('Back', self.ICON_Back, None, None)]
        for index, label in enumerate(('Move X', 'Move Y', 'Move Z', 'Extruder')[:3 + int(self.pd.HAS_HOTEND)]):
            value = position[index] * self.MINUNITMULT
            def painter(row, v=value, index=index):
                self._draw_axis_value(index, v, self.MBASE(row),
                                      self.lcd.Color_Bg_Black)
            entries.append((label, self.ICON_MoveX + index, value, painter))
        live = bool(getattr(self, '_live_jog', False))
        entries.append(('Live jog', ICON_LIVE_JOG, live,
            self._menu_checkbox_painter(live)))
        self._draw_list_menu('Move', entries, self.select_axis.now)

    def Popup_Window_Home(self, parking=False):
        self.Clear_Main_Window()
        self.Draw_Popup_Bkgd_60()
        show_theme_icon(self.lcd, self.ICON, self.ICON_BLTouch, 101, 105)
        if parking:
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * (7)) / 2, 230, "Parking")
        else:
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * (10)) / 2, 230, "Homing XYZ")

    def CompletedHoming(self):
        self.pd.HMI_flag.home_flag = False
        if (self.checkkey == self.Last_Prepare):
            self.checkkey = self.Prepare
            self.select_prepare.now = self.PREPARE_CASE_HOME
            self.index_prepare = self.MROWS
            self.Draw_Prepare_Menu()
        elif (self.checkkey == self.Back_Main):
            # dwin_zoffset = TERN0(HAS_BED_PROBE, probe.offset.z)
            # planner.finish_and_disable()
            self.Goto_MainMenu()

    def say_x(self, inset, line):
        self._draw_menu_text('X', self.LBLX + inset, line)

    def say_y(self, inset, line):
        self._draw_menu_text('Y', self.LBLX + inset, line)

    def say_z(self, inset, line):
        self._draw_menu_text('Z', self.LBLX + inset, line)

    def say_e(self, inset, line):
        self._draw_menu_text('E', self.LBLX + inset, line)
