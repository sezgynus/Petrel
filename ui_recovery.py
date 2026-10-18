"""Dedicated Klipper error panel with fixed recovery controls."""
import textwrap
from time import monotonic
from t5uic1_driver import T5UIC1Display


def error_lines(message, width=30):
    # Split control characters BEFORE the LCD's ASCII conversion, which would
    # otherwise replace newlines with '?'.
    result = []
    for paragraph in str(message).replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = T5UIC1Display._panel_text(paragraph.expandtabs(4))
        result.extend(textwrap.wrap(line, width) or [''])
    return tuple(result or ['No error details available'])


class RecoveryViewMixin:
    BOOT_CONNECTION_GRACE = 30.0
    RecoveryScreen = 50
    RECOVERY_TEXT_TOP = 56
    RECOVERY_TEXT_ROWS = 12
    RECOVERY_BUTTON_TOP = 330
    RECOVERY_BUTTON_HEIGHT = 44

    def _recovery_buttons(self):
        recovery = self.pd.recovery
        labels = {'restart': 'Restart Klipper', 'firmware': 'Firmware Restart',
                  'service': 'Restart Klipper service'}
        return tuple((a, labels[a]) for a in recovery.state.actions) + (('refresh', 'Refresh connection'),)

    def _recovery_lines(self):
        state = self.pd.recovery.state
        delayed = (getattr(self, '_boot_connection_delayed', False)
                   and state.kind not in ('error', 'shutdown'))
        return error_lines(('Printer is taking longer to connect.\n' if delayed else '')
                           + state.message)

    def Draw_Recovery(self):
        recovery = self.pd.recovery
        buttons = self._recovery_buttons()
        selected = max(-1, min(getattr(self, '_recovery_selection', len(buttons)-1), len(buttons)-1))
        self._recovery_selection = selected
        delayed = (getattr(self, '_boot_connection_delayed', False)
                   and recovery.state.kind not in ('error', 'shutdown'))
        lines = self._recovery_lines()
        offset = max(0, min(getattr(self, '_recovery_scroll', 0),
                            max(0, len(lines)-self.RECOVERY_TEXT_ROWS)))
        self._recovery_scroll = offset
        title = 'Printer connection' if delayed else recovery.state.title
        old = getattr(self, '_recovery_drawn', None)
        frame = (id(self.lcd), title, buttons)
        full = old is None or old['frame'] != frame
        if full:
            self.Clear_Popup_Area()
            self.Draw_Title(title)
            old = {'frame': frame, 'lines': (), 'hint': None, 'notice': None, 'buttons': {}}
        lcd = self.lcd
        visible = lines[offset:offset+self.RECOVERY_TEXT_ROWS]
        previous = old['lines']
        for i in range(max(len(previous), len(visible))):
            line = visible[i] if i < len(visible) else ''
            if full or i >= len(previous) or previous[i] != line:
                y = self.RECOVERY_TEXT_TOP+i*18
                lcd.draw_rectangle(1, lcd.Color_Bg_Black, 12, y, 259, y+17)
                if line:
                    lcd.draw_text(False, False, lcd.font8x16, lcd.Color_White,
                                  lcd.Color_Bg_Black, 12, y, line)
        hint = ('Turn: scroll / Press: keys' if selected == -1 else
                'Turn left past first: text')
        if hint != old['hint']:
            lcd.draw_rectangle(1, lcd.Color_Bg_Black, 12, 278, 259, 293)
            lcd.draw_text(False, False, lcd.font8x16, 0x7BEF, lcd.Color_Bg_Black, 12, 278, hint)
        if recovery.notice != old['notice']:
            lcd.draw_rectangle(1, lcd.Color_Bg_Black, 12, 296, 259, 327)
            for i, line in enumerate(error_lines(recovery.notice)[:2] if recovery.notice else ()):
                lcd.draw_text(False, False, lcd.font8x16, 0xFBAE,
                              lcd.Color_Bg_Black, 12, 296+i*16, line)
        states = {}
        for i, (action, label) in enumerate(buttons):
            active = i == selected
            disabled = recovery.busy and action != 'refresh'
            states[i] = (active, disabled)
            if not full and old['buttons'].get(i) == states[i]:
                continue
            y = self.RECOVERY_BUTTON_TOP+i*self.RECOVERY_BUTTON_HEIGHT
            fill = 0x063B if active else 0x18C4
            lcd.draw_rectangle(1, fill, 12, y, 259, y+35)
            lcd.draw_rectangle(0, lcd.Color_White if active else fill, 12, y, 259, y+35)
            lcd.draw_text(False, False, lcd.font8x16,
                          0x7BEF if disabled else lcd.Color_White, fill,
                          (272-len(label)*8)//2, y+10, label)
        self._recovery_drawn = dict(frame=frame, lines=visible, hint=hint,
                                    notice=recovery.notice, buttons=states)
        lcd.update()
        self._recovery_render = (recovery.state, recovery.notice, recovery.busy, selected, offset)

    def _poll_recovery_ui(self):
        recovery = getattr(self.pd, 'recovery', None)
        if recovery is None or not isinstance(getattr(recovery.state, 'kind', None), str):
            return False
        recovery.poll()
        if not self.pd.connection_error:
            if getattr(self, 'checkkey', None) == self.RecoveryScreen:
                self._recovery_render = None
                self._offline = False
                self.Goto_MainMenu()
                self.lcd.update()
            return False
        if getattr(self, '_relay_status', None) == 'off':
            return False
        if getattr(self, '_boot_active', False):
            if recovery.state.kind not in ('error', 'shutdown'):
                now = monotonic()
                started = getattr(self, '_boot_connection_started', None)
                if started is None:
                    started = self._boot_connection_started = now
                if now - started < self.BOOT_CONNECTION_GRACE:
                    return False
                self._boot_connection_delayed = True
            else:
                self._boot_connection_delayed = False
        first = getattr(self, 'checkkey', None) != self.RecoveryScreen
        if first:
            self._recovery_drawn = None
            if getattr(self, '_boot_animation_running', False):
                self.lcd.configure_animation(0, False, self._boot_animation_active_library,
                                            250, 254, self._boot_animation_x, 320, 10)
                self._boot_animation_running = False
            self._boot_active = False
            self.checkkey = self.RecoveryScreen
            self._recovery_scroll = 0
            self._recovery_actions = recovery.state.actions
            self._recovery_selection = len(self._recovery_buttons())-1
        if recovery.state.actions != getattr(self, '_recovery_actions', ()):
            self._recovery_selection = len(self._recovery_buttons())-1
            self._recovery_actions = recovery.state.actions
        signature = (recovery.state, recovery.notice, recovery.busy,
                     getattr(self, '_recovery_selection', 0), getattr(self, '_recovery_scroll', 0))
        if first or signature != getattr(self, '_recovery_render', None):
            self._recovery_render = signature
            self.Draw_Recovery()
        self._offline = True
        return True

    def _recovery_input(self, event):
        kind = event.kind
        if kind == 'button_release':
            if event.value >= self.SHORT_PRESS_MS:
                return
            kind = 'press'
        if kind not in ('rotate', 'press') or self._display_activity():
            return
        recovery = self.pd.recovery
        buttons = self._recovery_buttons()
        selected = getattr(self, '_recovery_selection', len(buttons)-1)
        if kind == 'rotate':
            if selected == -1:
                lines = self._recovery_lines()
                self._recovery_scroll = max(0, min(
                    max(0, len(lines)-self.RECOVERY_TEXT_ROWS),
                    getattr(self, '_recovery_scroll', 0)-event.value))
            else:
                self._recovery_selection = max(-1, min(len(buttons)-1, selected-event.value))
        elif selected == -1:
            self._recovery_selection = 0
        else:
            action = buttons[selected][0]
            if action == 'refresh':
                recovery.refresh()
            elif not recovery.busy:
                recovery.request(action)  # One explicit press, no extra dialog.
        self._recovery_render = None
        self.Draw_Recovery()
