"""Graphite background colors and icon compositing policy."""

BACKGROUND_COLOR = 0x2125
# Expand the LCD RGB565 value exactly, so opaque JPEG backing matches the UI.
_r, _g, _b = BACKGROUND_COLOR >> 11, (BACKGROUND_COLOR >> 5) & 63, BACKGROUND_COLOR & 31
BACKGROUND_RGB = ((_r << 3) | (_r >> 2), (_g << 2) | (_g >> 4), (_b << 3) | (_b >> 2))

# Small dashboard homing bars: graphite cyan / amber / neutral grey (RGB565).
AXIS_HOMED_COLOR = 0x063B
AXIS_UNHOMED_COLOR = 0xE507
AXIS_UNKNOWN_COLOR = 0x7BCF
# Muted Graphite coral: Klipper disconnected / shutdown.
KLIPPER_ERROR_COLOR = 0xD987


def show_icon(lcd, library, icons, x, y):
    # Filter the source JPEG's black backing to preserve the current surface.
    lcd.show_icon(library, icons, x, y, background=False, enhanced=True)


def draw_scrollbar(lcd, start, total, visible, y=90, height=253):
    """Draw the fixed right gutter shared by scrollable Graphite screens."""
    lcd.draw_rectangle(1, BACKGROUND_COLOR, 264, 84, 268, 355)
    if total > visible:
        thumb = max(10, height * visible // total)
        top = y + (height - thumb) * start // (total - visible)
        lcd.draw_rectangle(1, 0x39C8, 265, y, 267, y + height - 1)
        lcd.draw_rectangle(1, 0x063B, 265, top, 267, top + thumb - 1)
