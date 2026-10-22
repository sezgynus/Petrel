"""Reusable Core-gated NFC URI sharing control for Petrel's DWIN UI.

The UI never owns libnfc handles. A Core event refreshes capability visibility.
"""
from lcd_resources import ICON_NFC
from graphite_theme import show_icon as show_theme_icon


class NFCURIShareComponent:
    def __init__(self, core):
        self.core = core
        self.visible = False
        self._render = None
        self.sync()

    def sync(self):
        try:
            available = bool(
                self.core is not None
                and self.core.get_capabilities().get('ndef_uri_emulation') is True
                and self.core.is_ready())
        except (AttributeError, TypeError, ValueError):
            available = False
        changed = available != self.visible
        self.visible = available
        if changed:
            self._render = None
        return changed

    def info_item(self, url):
        return ('nfc_share', 'Share via NFC', url) if self.visible else None

    def start(self, url):
        # Revalidate once on explicit activation; no periodic device polling.
        self.sync()
        if not self.visible:
            raise OSError('NFC URI sharing is unavailable')
        return self.core.share_ndef_uri(url)

    def cancel(self):
        return self.core.cancel_share() if self.core is not None else False

    def invalidate(self):
        self._render = None

    def draw_button(self, view, y, selected):
        lcd = view.lcd
        state = (id(lcd), y, bool(selected))
        if state == self._render:
            return
        background = 0x063B if selected else 0x2967
        foreground = 0x10C4 if selected else lcd.Color_White
        lcd.draw_rectangle(1, lcd.Color_Bg_Black, 32, y - 4, 239, y + 23)
        show_theme_icon(lcd, view.ICON, ICON_NFC, 40, y)
        lcd.draw_text(False, False, lcd.font8x16, foreground,
                      background, 76, y + 2, 'Share via NFC')
        self._render = state

    def draw_popup(self, view, failed=False):
        lcd = view.lcd
        lcd.draw_rectangle(1, lcd.Color_Bg_Window, 14, 105, 258, 342)
        lcd.draw_rectangle(0, lcd.Line_Color, 14, 105, 258, 342)
        show_theme_icon(lcd, view.ICON, ICON_NFC, 126, 132)
        color = 0xF800 if failed else lcd.Popup_Text_Color
        lines = (
            ('NFC share failed', 'Check reader / retry', 'Press to close')
            if failed else
            ('Share Petrel link', 'Hold phone near reader', 'Press to cancel')
        )
        for index, label in enumerate(lines):
            lcd.draw_text(False, False, lcd.font8x16, color if index == 0 else
                          lcd.Popup_Text_Color, lcd.Color_Bg_Window,
                          (272 - len(label) * 8) // 2, 179 + index * 46, label)
