"""Encoder-operated notification overlay for the shared LCD UI."""
from petrel.artwork.resources import (
    ICON_NOTIFICATION_ACTION,
    ICON_NOTIFICATION_BELL,
    ICON_NOTIFICATION_DISMISS,
    ICON_NOTIFICATION_DOT,
)
from petrel.features.notifications.store import Retention
from petrel.hardware.dwin.driver import T5UIC1Display
from petrel.ui.theme import show_icon


class NotificationsViewMixin:
    _notification_visible_rows = 4

    def _notification_screen(self):
        screen = getattr(self, 'checkkey', None)
        return screen if screen in (
            self.MainMenu, self.Info, self.Prepare, self.Control, self.AxisMove,
            self.TemperatureID, self.Motion,
        ) else None

    def _notification_entries(self):
        store = getattr(self, 'notifications', None)
        if store is None or self._notification_screen() is None:
            return ()
        return store.snapshot()[1]

    def _draw_notification_control(self):
        screen = self._notification_screen()
        items = self._notification_entries()
        if not items or getattr(self, '_notification_focus', None) != screen:
            self._notification_focus = None
        selected = self._notification_focus is not None
        badge = str(len(items)) if len(items) <= 9 else '9+'
        key = (selected, badge) if items else None
        previous = getattr(self, '_notification_control_render', None)
        if key == previous:
            return False
        self._notification_control_render = key
        if key is not None and previous is None:
            self._paint_header_title(clear=True)
        if key is None:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Blue, 160, 3, 192, 27)
            self._paint_header_title(clear=True)
            if previous[0] and screen == self.MainMenu:
                self._draw_home_page(self.select_page.now)
            elif previous[0] and screen is not None and getattr(self, '_header_back_render', None):
                self._draw_header_back()
            return True
        if previous is None or previous[0] != selected:
            self.lcd.draw_rectangle(1, 0x19E9 if selected else self.lcd.Color_Bg_Blue,
                                    160, 3, 192, 27)
            show_icon(self.lcd, self.ICON, ICON_NOTIFICATION_BELL, 160, 6)
        else:
            self.lcd.draw_rectangle(1, 0x19E9 if selected else self.lcd.Color_Bg_Blue,
                                    179, 3, 192, 18)
        show_icon(self.lcd, self.ICON, ICON_NOTIFICATION_DOT, 179, 3)
        self.lcd.draw_text(False, False, self.lcd.font6x12, 0, 0,
                           179 + (14 - 6 * len(badge)) // 2, 5, badge)
        return True

    def _notification_boundary_input(self):
        if self.get_encoder_state() != self.ENCODER_DIFF_CCW or not self._notification_entries():
            return False
        selections = {
            self.MainMenu: 'select_page',
            self.Prepare: 'select_prepare',
            self.Control: 'select_control',
            self.AxisMove: 'select_axis',
            self.TemperatureID: 'select_temp',
            self.Motion: 'select_motion',
        }
        selected = (getattr(self, '_info_scroll', 0) if self.checkkey == self.Info
                    else getattr(self, selections[self.checkkey]).now)
        if selected == 0:
            self._notification_focus = self.checkkey
            self._draw_notification_control()
            if self.checkkey == self.MainMenu:
                self._draw_home_page(self.select_page.now)
            else:
                self._draw_header_back(False)
            return True
        return False

    def _notification_input(self):
        if getattr(self, 'notifications', None) is None:
            return False
        items = self._notification_entries()
        screen = self._notification_screen()
        event = self.get_encoder_state()
        if screen is not None and getattr(self, '_notification_overlay', None) == screen:
            if not items:
                self._close_notifications(redraw=True)
                return True
            keys = [None, *(item.identity for item in items)]
            selected = getattr(self, '_notification_selection', None)
            index = keys.index(selected) if selected in keys else 0
            if event == self.ENCODER_DIFF_ENTER:
                if index == 0:
                    self._close_notifications(redraw=True)
                else:
                    self._activate_notification(items, index - 1)
            elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                direction = 1 if event == self.ENCODER_DIFF_CW else -1
                steps = getattr(self, '_rotation_steps', 1)
                self._notification_selection = keys[(index + steps * direction) % len(keys)]
                self._draw_notification_panel()
            return True
        if screen is None or getattr(self, '_notification_focus', None) != screen or not items:
            return self._notification_boundary_input()
        if event == self.ENCODER_DIFF_ENTER:
            self._notification_overlay = screen
            self._notification_selection = None
            self._notification_start = 0
            self._notification_rows_render = None
            self._draw_notification_panel()
        elif event == self.ENCODER_DIFF_CW:
            self._notification_focus = None
            self._draw_notification_control()
            if screen == self.MainMenu:
                self._draw_home_page(self.select_page.now)
            else:
                self._draw_header_back()
        return True

    def _activate_notification(self, items, index):
        item = items[index]
        if item.action:
            handler = self.notification_actions.get(item.action)
            if handler is not None:
                origin = self.checkkey
                self._close_notifications(redraw=False)
                accepted = handler(item)
                if accepted is not False and item.retention is Retention.DISMISSIBLE:
                    self.notifications.dismiss(item)
                if self.checkkey == origin:
                    self._restore_notification_underlay()
            return
        if item.retention is Retention.DISMISSIBLE and self.notifications.dismiss(item):
            remaining = self._notification_entries()
            if not remaining:
                self._close_notifications(redraw=True)
            else:
                self._notification_selection = remaining[min(index, len(remaining) - 1)].identity
                self._draw_notification_panel()
            self._draw_notification_control()

    def _close_notifications(self, *, redraw):
        self._notification_overlay = None
        self._notification_rows_render = None
        if not self._notification_entries():
            self._notification_focus = None
        if redraw:
            self._restore_notification_underlay()

    def _restore_notification_underlay(self):
        # Panels cannot read back the framebuffer. Restore the originating
        # menu body using its renderer; the dashboard remains untouched.
        self._list_render = None
        self._info_render_scroll = None
        self._notification_restoring = True
        try:
            self._redraw_current_screen()
        finally:
            self._notification_restoring = False
        self._draw_notification_control()

    def _draw_notification_panel(self, *, invalidate=False):
        screen = self._notification_screen()
        if screen is None or getattr(self, '_notification_overlay', None) != screen:
            return False
        items = self._notification_entries()
        if not items:
            return False
        selected = self._notification_selection
        index = next((i for i, item in enumerate(items) if item.identity == selected), -1)
        self._notification_selection = items[index].identity if index >= 0 else None
        limit = self._notification_visible_rows
        start = max(0, min(self._notification_start, len(items) - limit))
        start = 0 if index < 0 else max(min(start, index), index - limit + 1)
        self._notification_start = start
        visible = items[start:start + limit]
        signatures = tuple((item, start + i == index) for i, item in enumerate(visible))
        frame = (index < 0, start, len(items))
        previous = None if invalidate else self._notification_rows_render
        if previous == (frame, signatures):
            return False
        lcd = self.lcd
        background = lcd.Color_Bg_Window
        if previous is None:
            lcd.draw_rectangle(1, background, 20, 34, 262, 230)
            lcd.draw_rectangle(0, lcd.Line_Color, 20, 34, 262, 230)
            self._notification_text('Notifications', 51, 41, background)
        if previous is None or previous[0][0] != frame[0]:
            lcd.draw_rectangle(1, 0x19E9 if frame[0] else background, 24, 37, 47, 60)
            show_icon(lcd, self.ICON, self.ICON_Back, 26, 39)
        if previous is None or previous[0][1:] != frame[1:]:
            lcd.draw_rectangle(1, background, 256, 62, 260, 228)
            if len(items) > limit:
                track = 167
                height = max(10, track * limit // len(items))
                top = 62 + (track - height) * start // (len(items) - limit)
                lcd.draw_rectangle(1, lcd.Rectangle_Color, 257, top, 259, top + height - 1)
        old_rows = previous[1] if previous else ()
        for slot in range(max(len(old_rows), len(signatures))):
            value = signatures[slot] if slot < len(signatures) else None
            if slot < len(old_rows) and old_rows[slot] == value:
                continue
            y = 62 + slot * 41
            active = value is not None and value[1]
            color = 0x19E9 if active else background
            lcd.draw_rectangle(1, color, 23, y, 254, y + 40)
            if value is None:
                continue
            item = value[0]
            self._notification_text(item.title, 31, y + 3, color)
            self._notification_text(item.detail, 31, y + 21, color, small=True)
            icon = (ICON_NOTIFICATION_ACTION if item.action else
                    ICON_NOTIFICATION_DISMISS if item.retention is Retention.DISMISSIBLE else None)
            if icon is not None:
                show_icon(lcd, self.ICON, icon, 236, y + 12)
        self._notification_rows_render = (frame, signatures)
        return True

    def _notifications_cover_screen(self):
        return getattr(self, '_notification_overlay', None) is not None and (
            self._notification_overlay == self.checkkey)

    def _sync_notification_overlay(self):
        overlay = getattr(self, '_notification_overlay', None)
        if overlay is None:
            return False
        if overlay != self._notification_screen():
            self._close_notifications(redraw=False)
            return False
        if not self._notification_entries():
            self._close_notifications(redraw=True)
            return True
        return self._draw_notification_panel()

    def _notification_text(self, value, x, y, background, *, small=False):
        max_cells = 32 if small else 24
        value = T5UIC1Display._panel_text(value)
        if len(value) > max_cells:
            value = value[:max_cells - 3] + '...'
        font = self.lcd.font6x12 if small else self.lcd.font8x16
        self.lcd.draw_text(False, False, font, self.lcd.Color_White, background, x, y, value)
