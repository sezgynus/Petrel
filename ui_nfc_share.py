"""Reusable Core-gated NFC URI sharing control for Petrel's DWIN UI.

The UI never owns libnfc handles. A Core event refreshes capability visibility.
"""
from lcd_resources import (ICON_NFC_SHARE_NORMAL, ICON_NFC_SHARE_SELECTED, ICON_LIBRARY_ID,
                           ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST)
from graphite_theme import show_icon as show_theme_icon


class NFCURIShareComponent:
    def __init__(self, core):
        self.core = core
        self.visible = False
        self._render = None
        self._animation_lcd = None
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

    def info_item(self, version):
        return ('nfc_share', 'Petrel', version) if self.visible else None

    def start(self, url):
        # Revalidate once on explicit activation; no periodic device polling.
        self.sync()
        if not self.visible:
            raise OSError('NFC URI sharing is unavailable')
        return self.core.share_ndef_uri(url)

    def cancel(self):
        return self.core.cancel_share() if self.core is not None else False

    def stop_animation(self):
        lcd, self._animation_lcd = self._animation_lcd, None
        if lcd is not None and getattr(lcd, "_closed", False) is not True:
            lcd.configure_animation(2, False, ICON_LIBRARY_ID,
                                    ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST,
                                    56, 116, 20)

    def invalidate(self):
        self.stop_animation()
        self._render = None

    def draw_button(self, view, y, selected):
        lcd = view.lcd
        state = (id(lcd), y, bool(selected))
        if state == self._render:
            return
        # Clear both states before drawing; normal has no focus border.
        top = y - 2
        lcd.draw_rectangle(1, lcd.Color_Bg_Black, 92, top, 111, top + 19)
        icon = ICON_NFC_SHARE_SELECTED if selected else ICON_NFC_SHARE_NORMAL
        show_theme_icon(lcd, ICON_LIBRARY_ID, icon, 92, top)
        self._render = state

    def draw_popup(self, view, failed=False):
        lcd = view.lcd
        self.stop_animation()
        lcd.draw_rectangle(1, lcd.Color_Bg_Window, 14, 72, 258, 361)
        lcd.draw_rectangle(0, lcd.Line_Color, 14, 72, 258, 361)
        color = 0xF800 if failed else lcd.Popup_Text_Color
        lines = (
            ('NFC share failed', 'Check reader / retry', 'Press to close')
            if failed else
            ('Share Petrel link', 'Hold phone near reader', 'Press to cancel')
        )
        for y, label in zip((88, 291, 329), lines):
            lcd.draw_text(False, False, lcd.font8x16, color if y == 88 else
                          lcd.Popup_Text_Color, lcd.Color_Bg_Window,
                          (272 - len(label) * 8) // 2, y, label)
        if failed:
            lcd.show_icon(ICON_LIBRARY_ID, ICON_NFC_SHARE_FIRST, 56, 116)
        else:
            # 0x28 interval is in 10 ms units; the panel advances all 12 frames.
            lcd.configure_animation(2, True, ICON_LIBRARY_ID,
                                    ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST,
                                    56, 116, 20)
            self._animation_lcd = lcd
