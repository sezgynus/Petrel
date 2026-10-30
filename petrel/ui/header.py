"""Existing display methods grouped by responsibility."""
from petrel.ui.theme import show_icon as show_theme_icon
from petrel.artwork.resources import ICON_WIFI_POOR, ICON_WIFI_MEDIUM, ICON_WIFI_STRONG, ICON_PROGRESS_TRACK, ICON_PROGRESS_FILL
from petrel.features.info.system import wifi_signal_level
import time
from petrel.hardware.dwin.driver import T5UIC1Display


class HeaderMixin:
    def _invalidate_header(self):
        self._header_back_render = None
        self._header_clock_drawn = None
        self._header_wifi_drawn = None
        self._header_klipper_drawn = None

    def _draw_header_back(self, selected=True):
        """Fixed return control, independent of the scrolling body."""
        state = (id(self.lcd), bool(selected))
        if getattr(self, '_header_back_render', None) == state:
            return
        self._header_back_render = state
        self.lcd.draw_rectangle(1, 0x19E9 if selected else self.lcd.Color_Bg_Blue,
                                4, 3, 27, 26)
        show_theme_icon(self.lcd, self.ICON, self.ICON_Back, 6, 5)

    def Draw_Title(self, title, back=False):
        # Wi-Fi begins at x=193; the clock shifts left for the 8x8 state cap.
        # Wi-Fi begins at x=193; an 8x16 title gets at most 22 cells,
        # leaving a three-pixel gap before the status cluster.
        title = T5UIC1Display._panel_text(str(title))
        cells = 19 if back else 22
        if len(title)>cells:
            title = title[:cells-3]+'...'
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Blue, 34 if back else 14, 6, title)
        self._draw_header_clock()

    def _draw_wifi_signal(self):
        # Native JPEG backgrounds are black; Graphite's enhanced filter makes
        # those pixels transparent. Clear the old icon only when its band changes.
        info = self.pd.system_info
        ssid = info.get('wifi_ssid')
        level = wifi_signal_level(info.get('wifi_rssi')) if ssid not in (None, 'Unavailable', 'Disconnected') else None
        icon = {'Poor': ICON_WIFI_POOR, 'Medium': ICON_WIFI_MEDIUM,
                'Strong': ICON_WIFI_STRONG}.get(level)
        key = (id(self.lcd), icon)
        previous = getattr(self, '_header_wifi_drawn', None)
        if key == previous:
            return False
        self._header_wifi_drawn = key
        if icon is None and previous is None:
            return False
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Blue, 193, 4, 212, 23)
        if icon is not None:
            show_theme_icon(self.lcd, self.ICON, icon, 193, 4)
        return True

    def _draw_klipper_state(self):
        # Reuse the actual progress-bar JPEG caps: ready is the fill color,
        # every non-ready state is the track color. Recoloring those assets
        # therefore updates both the progress bar and this indicator.
        # No polling or additional LCD library resources are needed.
        connection = self.pd.state.connection
        error = bool(self.pd.connection_error)
        icon = ICON_PROGRESS_FILL if connection == 'ready' and not error else ICON_PROGRESS_TRACK
        key = (id(self.lcd), connection, error, icon)
        if key == getattr(self, '_header_klipper_drawn', None):
            return False
        # Wi-Fi ends at x=212; clock stays x=214..253; cap x=259..266.
        # The 8x8 artwork is centered between the clock and the right edge.
        # Clock y=6..21 and cap y=10..17 share the same vertical center.
        # Clear before changing caps: enhanced JPEG drawing leaves black
        # background pixels transparent and must not retain the previous state.
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Blue, 259, 10, 266, 17)
        show_theme_icon(self.lcd, self.ICON, icon, 259, 10)
        self._header_klipper_drawn = key
        return True

    def _draw_header_clock(self):
        value = time.strftime('%H:%M', time.localtime())
        key = (id(self.lcd), value)
        clock_changed = key != getattr(self, '_header_clock_drawn', None)
        if clock_changed:
            self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                               self.lcd.Color_Bg_Blue, 214, 6, value)
            self._header_clock_drawn = key
        wifi_changed = self._draw_wifi_signal()
        klipper_changed = self._draw_klipper_state()
        return clock_changed or wifi_changed or klipper_changed
