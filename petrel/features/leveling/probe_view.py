"""Existing display methods grouped by responsibility."""
import textwrap
from petrel.hardware.dwin.driver import T5UIC1Display


class ProbeViewMixin:
    def _probe_options(self):
        wizard = self.pd.probe_wizard
        if wizard.phase == 'active':
            return tuple((step, lambda step=step: wizard.testz(step))
                         for step in ('--', '-', '+', '++')) + (('Cancel', wizard.abort), ('Accept', wizard.accept))
        if wizard.phase == 'accepted':
            return (('Save', wizard.save), ('Continue', self._leave_probe))
        if wizard.phase in ('error', 'interrupted'):
            if self.pd.state.ready and not self.pd.connection_error and not wizard.active():
                return (('Back', self._leave_probe), ('Retry', wizard.start))
            return (('Back', self._leave_probe),)
        if wizard.phase == 'saved':
            return (('Back', self._leave_probe),)
        return (('Back', self._leave_probe), ('Start', wizard.start))

    def _leave_probe(self):
        self._drawn_probe_wizard = None
        self._return_to_mesh_menu()

    def _probe_button(self, label, box, selected):
        x, y, width, height = box
        self.lcd.draw_rectangle(1, 0x03B5, x, y, x+width, y+height)
        self.lcd.draw_rectangle(0, self.lcd.Color_White if selected else 0x03B5,
                                x-2, y-2, x+width+2, y+height+2)
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                           0x03B5, x+(width-len(label)*8)//2, y+(height-16)//2, label)

    def Draw_Probe_Wizard(self):
        wizard = self.pd.probe_wizard
        manual = self.pd.state.status.get('manual_probe', {})
        options = self._probe_options()
        selected = max(0, min(getattr(self, '_probe_selection', 0), len(options)-1))
        self._probe_selection = selected
        layout = ('active' if wizard.phase == 'active' else 'accepted' if wizard.phase == 'accepted'
                  else 'error' if wizard.phase in ('error', 'interrupted')
                  else 'saved' if wizard.phase == 'saved' else 'start')
        values = tuple(manual.get(key) for key in ('z_position_lower', 'z_position', 'z_position_upper'))
        error = wizard.message if layout == 'error' or getattr(self, '_probe_ui_error', None) else None
        if getattr(self, '_probe_ui_error', None): error = self._probe_ui_error
        signature = (layout, values, selected, error)
        previous = getattr(self, '_drawn_probe_wizard', None)
        if signature == previous:
            return
        full = previous is None or previous[0] != layout
        if full:
            self.Clear_Main_Window()
            self.Draw_Title('Probe calibration', back=any(label == 'Back' for label, _ in options))
        if layout == 'active':
            if full or previous[1] != values:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 72, 263, 148)
                def value_text(value):
                    return '{:.3f}'.format(value) if isinstance(value, (int, float)) else '---'
                for value, x, width, font, y in (
                        (values[0], 8, 68, self.lcd.font8x16, 96),
                        (values[1], 84, 104, self.lcd.font14x28, 86),
                        (values[2], 196, 68, self.lcd.font8x16, 96)):
                    label = value_text(value)
                    char_width = 14 if x == 84 else 8
                    self.lcd.draw_text(False, False, font, self.lcd.Color_White,
                                       self.lcd.Color_Bg_Black, x+max(0,(width-len(label)*char_width)//2), y, label)
                self.lcd.draw_text(False, False, self.lcd.font6x12, self.lcd.Color_White,
                                   self.lcd.Color_Bg_Black, 130, 123, 'mm')
            boxes = ((12,174,52,44), (77,174,52,44), (142,174,52,44), (207,174,52,44),
                     (26,294,99,40), (146,294,99,40))
        else:
            boxes = ((26,294,99,40), (146,294,99,40))
            if full:
                label = {'start': 'Ready to calibrate', 'accepted': 'Offset accepted',
                         'saved': 'Saved', 'error': 'Calibration interrupted'}[layout]
                self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                                   self.lcd.Color_Bg_Black, (272-len(label)*8)//2, 110, label)
        for index, (label, _) in enumerate(options):
            if label == 'Back':
                self._draw_header_back(index == selected)
                continue
            if full or selected != previous[2] and index in (selected, previous[2]):
                self._probe_button(label, boxes[index], index == selected)
        if error:
            import textwrap
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 235, 263, 280)
            for line, text in enumerate(textwrap.wrap(T5UIC1Display._panel_text(error), 40)[:3]):
                self.lcd.draw_text(False, False, self.lcd.font6x12, self.lcd.Color_White,
                                   self.lcd.Color_Bg_Black, 12, 238+line*14, text)
        elif previous and previous[3]:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 235, 263, 280)
        self._drawn_probe_wizard = signature
        self.lcd.update()

    def HMI_Probe_Wizard(self):
        wizard = self.pd.probe_wizard
        wizard.update()
        options = self._probe_options()
        self._probe_selection = max(0, min(getattr(self, '_probe_selection', 0), max(0, len(options) - 1)))
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_CW and options:
            self._probe_selection = min(len(options) - 1, self._probe_selection + getattr(self,"_rotation_steps",1))
        elif event == self.ENCODER_DIFF_CCW:
            self._probe_selection = max(0, self._probe_selection - getattr(self,"_rotation_steps",1))
        elif event == self.ENCODER_DIFF_ENTER and options and not wizard.pending:
            try:
                self._probe_ui_error = None
                options[self._probe_selection][1]()
            except ValueError as error:
                self._probe_ui_error = str(error)
        if self.checkkey == self.ProbeWizardID:
            self.Draw_Probe_Wizard()

    def _open_zoffset(self, mode, row):
        row = self._menu_row(self.PREPARE_CASE_ZOFF if mode == -4 else self.TUNE_CASE_ZOFF)
        self._zoffset_edit_row = self._invalidate_list_row(row)
        self.checkkey = self.Homeoffset
        self.pd.HMI_ValueStruct.show_mode = mode
        self._zoffset_target = self.pd.BABY_Z_VAR * 100
        self._draw_offset_value(self._zoffset_target,self.MBASE(row),self.lcd.Select_Color)

    def HMI_Zoffset(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        if not hasattr(self, '_zoffset_target'):
            self._zoffset_target = self.pd.HMI_ValueStruct.offset_value
        zoff_line = 0
        if self.pd.HMI_ValueStruct.show_mode == -4:
            zoff_line = self.PREPARE_CASE_ZOFF + self.MROWS - self.index_prepare
        else:
            zoff_line = self.TUNE_CASE_ZOFF + self.MROWS - self.index_tune

        zoff_line = getattr(self, '_zoffset_edit_row', zoff_line)
        if (encoder_diffState == self.ENCODER_DIFF_ENTER): #if (applyencoder(encoder_diffstate, offset_value))
            self._action("Runtime Z offset", lambda: self.pd.setZOffset(self._zoffset_target / 100.0, idle_only=self.pd.HMI_ValueStruct.show_mode == -4), silent=True)

            self.checkkey = self.Prepare if self.pd.HMI_ValueStruct.show_mode == -4 else self.Tune
            self._draw_offset_value(self._zoffset_target,self.MBASE(zoff_line),self.lcd.Color_Bg_Black)

            self.lcd.update()
            return

        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self._zoffset_target += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self._zoffset_target -= self._encoder_move_value

        if (self._zoffset_target < (self.pd.Z_PROBE_OFFSET_RANGE_MIN) * 100):
            self._zoffset_target = self.pd.Z_PROBE_OFFSET_RANGE_MIN * 100
        elif (self._zoffset_target > (self.pd.Z_PROBE_OFFSET_RANGE_MAX) * 100):
            self._zoffset_target = self.pd.Z_PROBE_OFFSET_RANGE_MAX * 100

        self.last_zoffset = self.dwin_zoffset
        self.dwin_zoffset = self._zoffset_target / 100.0

        self._draw_offset_value(self._zoffset_target,self.MBASE(zoff_line),self.lcd.Select_Color)
        self.lcd.update()
