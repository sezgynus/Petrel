"""DACAI panels that emulate the DWIN T5UIC1 protocol (e.g. Ender 3 Max Neo).

Creality ships some printers with a Guangzhou DACAI panel (Allwinner F1C100s,
microSD folder ``private`` instead of ``DWIN_SET``) whose firmware emulates
most of the T5UIC1 command set. The differences handled here were measured on
a Max Neo panel; see docs/dacai.md:

* SRAM JPEGs are drawn with 0x70 (0x24 is not implemented).
* 0x27 bit 7 is inverted: set = black transparent, clear = opaque.
* 0x27 copies one row more than asked (rows y0..y1+1; columns are exact).
* 0x09 moving left or up treats x1/y1 as exclusive; right and down are exact.
* 0x33 stores the whole 32 KB SRAM as ``image/<id>.jpg`` and the loader
  requires FF D9 at the end of the file, so JPEGs are padded to 32 KB.
* Icon files cannot be written over UART. Icons are packed onto JPEG sprite
  sheets (petrel.artwork.sprites) and drawn with 0x25 + 0x27; animations
  (0x28) are stepped by the host.
* 0x03 draws only horizontal and vertical segments; a diagonal segment
  becomes one L-shaped step. Diagonals are sent as pixel staircases.
* Data-Flash writes are acknowledged with a bare ``A5 'OK'``.
* 0x30 is clamped to 0..63; 0x38 re-clocks the host UART until power loss.
* Picture IDs above 15 are accepted.
* There is no auxiliary UART: 0x38 re-clocks the host link and 0x39 is not
  implemented, so the DWIN auxiliary-UART feature is rejected.
"""
import logging
import os
import struct
import time

import serial

from petrel.hardware.dwin.driver import T5UIC1Display, T5UIC1TimeoutError

UART_CLOCK = 15667200
DEFAULT_BAUD = 115200
HOST_BAUDS = (115200, 230400, 460800, 921600)
PICTURE_SIZE = 0x8000


class UnsupportedPanelFeature(RuntimeError):
    """A DWIN T5UIC1 feature that DACAI panels do not provide."""


def enabled():
    """Panel type selected in configure.sh (PETREL_DACAI)."""
    return os.environ.get('PETREL_DACAI') == '1'


def configured_baud():
    """Host UART speed for DACAI panels; anything unsupported stays at 115200."""
    try:
        baud = int(os.environ.get('PETREL_DACAI_BAUD') or DEFAULT_BAUD)
    except ValueError:
        baud = DEFAULT_BAUD
    if baud not in HOST_BAUDS:
        logging.warning('Unsupported PETREL_DACAI_BAUD %r; using %d', baud, DEFAULT_BAUD)
        return DEFAULT_BAUD
    return baud


def check_transport():
    """DACAI cannot share its UART through the DWIN auxiliary-UART broker.

    The broker's receive parser rejects DACAI's bare acknowledgements, and its
    auxiliary baud command (0x38) changes the DACAI host link speed instead.
    """
    if enabled() and os.environ.get('PETREL_DWIN_SOCKET'):
        raise UnsupportedPanelFeature(
            'PETREL_DACAI=1 cannot use the DWIN auxiliary UART broker '
            '(PETREL_DWIN_SOCKET); run ./configure.sh to remove it')


def staircase(x0, y0, x1, y1):
    """Axis-aligned polyline points that rasterize the segment like a line.

    Pixels follow the segment along its major axis (minor coordinate rounded
    half up); runs of equal minor coordinate are joined by one-pixel steps.
    """
    dx, dy = x1 - x0, y1 - y0
    if not dx or not dy:
        return [(x0, y0), (x1, y1)]
    steep = abs(dy) > abs(dx)
    if steep:  # rasterize along y, then swap back
        x0, y0, x1, y1, dx, dy = y0, x0, y1, x1, dy, dx
    major, minor = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    runs = []  # [minor offset, first major, last major]
    for i in range(abs(dx) + 1):
        offset = (2 * i * abs(dy) + abs(dx)) // (2 * abs(dx))
        x = x0 + major * i
        if runs and runs[-1][0] == offset:
            runs[-1][2] = x
        else:
            runs.append([offset, x, x])
    points = []
    for offset, first, last in runs:
        y = y0 + minor * offset
        if points:
            points.append((points[-1][0], y))  # one-pixel step on the minor axis
        points += [(first, y), (last, y)]
    if steep:
        points = [(y, x) for x, y in points]
    path = [points[0]]
    for point in points[1:]:
        if point == path[-1]:
            continue
        if len(path) >= 2 and (path[-2][0] == path[-1][0] == point[0]
                               or path[-2][1] == path[-1][1] == point[1]):
            path[-1] = point  # extend a straight run instead of adding a corner
        else:
            path.append(point)
    return path


def picture_payload(data, size=PICTURE_SIZE):
    """Pad a JPEG with a COM segment to exactly ``size`` bytes.

    0x33 writes the complete SRAM as the picture file; the DACAI loader rejects
    files that do not end with FF D9.
    """
    data = bytes(data)
    if data[:2] != b'\xff\xd8' or data[-2:] != b'\xff\xd9':
        raise ValueError('picture must be a complete JPEG')
    pad = size - len(data) - 4
    if pad < 0:
        raise ValueError(f'JPEG too large for one DACAI picture (max {size - 4} bytes)')
    return data[:2] + b'\xff\xfe' + struct.pack('>H', pad + 2) + bytes(pad) + data[2:]


class DacaiDriver(T5UIC1Display):
    PANEL_PROTOCOL = 'dacai'
    PICTURE_ID_MAX = 255
    BARE_FLASH_ACK = True
    # 0x70 draws SRAM JPEGs opaque: thumbnails must carry their own background.
    OPAQUE_SRAM_JPEG = True
    # The firmware clamps 0x30 to 0..63 (63 = 100 %); 4 is the darkest usable level.
    BACKLIGHT_MAX = 63
    BACKLIGHT_MIN = 4

    def __init__(self, *args, host_baud=None, **kwargs):
        check_transport()
        self.host_baud = configured_baud() if host_baud is None else host_baud
        self._sprites = None
        self._sprite_animations = {}
        self._sprite_mask = 0xFFFF
        self._assets_synced = False
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Host link
    # ------------------------------------------------------------------

    def _after_handshake(self):
        # The startup probe may have found the panel at another speed left
        # over from an interrupted session; always end at the configured one.
        if isinstance(self.serial, serial.Serial):
            self._switch_baud(self.host_baud)

    def _send_baud(self, baud):
        with self._transaction_lock:
            self._send(0x38, self._word(max(1, round(UART_CLOCK / baud))))
            self.serial.flush()
        time.sleep(.05)
        self.serial.baudrate = baud
        self._rx.clear()

    def _switch_baud(self, target):
        if self.serial.baudrate == target:
            return
        self._send_baud(target)
        for _ in range(3):
            if self.handshake(.5):
                logging.info('DACAI host UART set to %d baud', target)
                return
        logging.warning('DACAI baud switch to %d failed; staying at %d', target, DEFAULT_BAUD)
        self._send_baud(DEFAULT_BAUD)
        if not self.handshake(1.0):
            raise T5UIC1TimeoutError('DACAI baud fallback handshake timed out')

    def close(self):
        if (not getattr(self, '_closed', False) and isinstance(self.serial, serial.Serial)
                and self.serial.baudrate != DEFAULT_BAUD):
            # The panel keeps 0x38 until power loss: leave it at its power-on
            # speed so a restarted Petrel finds it immediately.
            try:
                divisor = round(UART_CLOCK / DEFAULT_BAUD)
                self.serial.write(self.HEADER + bytes((0x38,)) + self._word(divisor) + self.TAIL)
                self.serial.flush()
            except Exception:
                logging.debug('DACAI baud reset on close failed', exc_info=True)
        super().close()

    # ------------------------------------------------------------------
    # Protocol differences
    # ------------------------------------------------------------------

    def set_backlight(self, brightness):
        level = self._u8(brightness, 'brightness')
        if level:
            level = max(self.BACKLIGHT_MIN, (level * self.BACKLIGHT_MAX + 127) // 255)
        self._send(0x30, bytes((level,)))
        self._backlight_raw = brightness

    def show_sram_jpeg(self, x, y, address=0, *, background=True, enhanced=False):
        if not isinstance(address, int) or not 0 <= address < self.SRAM_SIZE:
            raise ValueError('SRAM address outside 32KB range')
        # 0x24 is not implemented; 0x70 draws the SRAM JPEG opaque.
        self._send(0x70, self._words(x, y, address))

    def move_area(self, mode, direction, distance, color, x0, y0, x1, y1):
        # Moving left (0) or up (2) treats x1/y1 as exclusive: the last
        # column/row stays and the fill starts one early, leaving a line per
        # move. Right and down are exact.
        if direction == 0:
            x1 = min(x1 + 1, self.WIDTH)
        elif direction == 2:
            y1 = min(y1 + 1, self.HEIGHT)
        super().move_area(mode, direction, distance, color, x0, y0, x1, y1)

    def copy_cache(self, cache_id, x0, y0, x1, y1, x, y, *,
                   background=False, restore=False, enhanced=True):
        # Bit 7 has the opposite meaning: set = black transparent.
        # The panel copies rows y0..y1+1, so the last row is sent one lower.
        # A one-row copy at y = 0 cannot be expressed and copies two rows.
        super().copy_cache(cache_id, x0, y0, x1, max(y1 - 1, 0), x, y,
                           background=not background,
                           restore=restore, enhanced=enhanced)

    def prepare_picture(self, data):
        return picture_payload(data)

    def draw_polyline(self, color, points):
        points = tuple(points)
        if len(points) < 2:
            raise ValueError("a polyline needs at least two points")
        for point in points:
            if not isinstance(point, (tuple, list)) or len(point) != 2:
                raise ValueError("points must contain (x, y) pairs")
        path = [tuple(points[0])]
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            for point in staircase(self._u16(x0), self._u16(y0),
                                   self._u16(x1), self._u16(y1))[1:]:
                if point != path[-1]:
                    path.append(point)
        if len(path) == 1:
            path.append(path[0])
        # One 0x03 frame holds at most 61 points; chunks share their end point.
        limit = (self.MAX_DATA_LENGTH - 2) // 4
        for start in range(0, len(path) - 1, limit - 1):
            super().draw_polyline(color, path[start:start + limit])

    # DWIN auxiliary UART (0x38/0x39): not available on DACAI. The panel's own
    # host-link speed switch is _send_baud, used only by this driver.
    def set_aux_baud_divisor(self, divisor):
        raise UnsupportedPanelFeature('DACAI panels have no auxiliary UART')

    def set_aux_baudrate(self, baudrate):
        raise UnsupportedPanelFeature('DACAI panels have no auxiliary UART')

    def aux_write(self, data):
        raise UnsupportedPanelFeature('DACAI panels have no auxiliary UART')

    def poll_aux_data(self):
        raise UnsupportedPanelFeature('DACAI panels have no auxiliary UART')

    # ------------------------------------------------------------------
    # Icons from sprite sheets
    # ------------------------------------------------------------------

    def _startup_animation_library(self):
        from petrel.artwork import sprites
        from petrel.artwork.resources import ICON_LIBRARY_ID
        try:
            current = sprites.load()
            if sprites.resident(self, current):
                self._sprites = current.index
                return ICON_LIBRARY_ID
        except Exception:
            logging.exception('Sprite sheets unavailable')
        return None  # First install: draw the boot frame without icons.

    def _startup_sync_icons(self):
        # Failures propagate like the DWIN icon-library sync: the panel's own
        # icon files are not Petrel's, so there is no silent fallback.
        self.sync_sprites()

    def sync_sprites(self, *, force=False):
        """Upload changed sheets; ``force`` repairs pictures removed by a microSD update.

        Raises on any upload or verification failure; the sheets are used only
        after their metadata checkpoint has been verified. This method alone
        owns ``_sprites`` and ``_assets_synced``: both are cleared before any
        picture is touched and set again only after a verified sync, so a
        failed resync leaves the driver unsynchronized and without an index.
        """
        from petrel.artwork import sprites
        self._assets_synced = False
        self._sprite_animations.clear()
        self._sprites = None
        # Picture slots may be rewritten: reload the sheet before the next copy.
        self._cached_picture1 = None
        current = sprites.load()
        sprites.sync(self, force=force, sprites=current)
        self._sprites = current.index
        self._assets_synced = True

    def show_icon(self, library_id, icon_ids, x, y, *, background=True,
                  restore=False, enhanced=False):
        icons = (icon_ids,) if isinstance(icon_ids, int) else tuple(icon_ids)
        if not self._managed_library(library_id):
            super().show_icon(library_id, icon_ids, x, y, background=background,
                              restore=restore, enhanced=enhanced)
            return
        if not icons:
            raise ValueError("at least one icon ID is required")
        if self._sprites is None:
            # No verified sheets: skip rather than draw the panel's own icon
            # files with 0x23, which do not hold Petrel's artwork.
            logging.debug('DACAI sprite sheets unavailable; icons %s skipped', icons)
            return
        self._draw_sprites(icons, x, y, background)

    @staticmethod
    def _managed_library(library_id):
        """Petrel's own library: always drawn from the sprite sheets, never natively."""
        from petrel.artwork.resources import ICON_LIBRARY_ID
        return library_id == ICON_LIBRARY_ID

    def _draw_sprites(self, icons, x, y, background):
        """Copy icons from their sheets in a row; False if any icon is missing.

        Missing icons are skipped rather than drawn with 0x23: the panel's own
        icon files do not hold Petrel's artwork.
        """
        from petrel.artwork.sprites import FIRST_SLOT
        complete = True
        for icon in icons:
            pieces = self._sprites.get(icon)
            if not pieces:
                logging.warning('Icon %s is not on the DACAI sprite sheets', icon)
                complete = False
                continue
            for sheet, x0, y0, width, height, dx, dy in pieces:
                self.ensure_cached_picture(FIRST_SLOT + sheet)
                self.copy_cache(1, x0, y0, x0 + width - 1, y0 + height - 1, x + dx, y + dy,
                                background=background, enhanced=False)
            x += pieces[0][3]
        return complete

    def configure_animation(self, animation_id, enabled, library_id,
                            first_icon, last_icon, x, y, interval,
                            *, restart_from_first=True):
        if self._sprite_animation(animation_id, enabled, library_id, first_icon,
                                  last_icon, x, y, interval, restart_from_first):
            return
        super().configure_animation(animation_id, enabled, library_id, first_icon,
                                    last_icon, x, y, interval,
                                    restart_from_first=restart_from_first)

    def set_animation_mask(self, state):
        super().set_animation_mask(state)
        self._sprite_mask = state

    def _sprite_animation(self, animation_id, enabled, library_id, first_icon, last_icon,
                          x, y, interval, restart_from_first):
        """Host-side replacement for 0x28 for the managed library.

        Returns False only for other libraries. Requests for the managed
        library never reach 0x28: without verified sheets they are dropped.
        """
        if not self._managed_library(library_id):
            return False
        if not 0 <= animation_id <= 15:
            raise ValueError('animation ID must be 0..15')
        frames = range(first_icon, last_icon + 1)
        if self._sprites is None or not frames:
            if enabled:
                logging.debug('DACAI animation %d skipped: no sprite sheets or frames',
                              animation_id)
            self._sprite_animations.pop(animation_id, None)
            return True
        missing = [icon for icon in frames if icon not in self._sprites]
        if missing:
            # Never fall back to 0x28: the native icon files are not Petrel's.
            logging.warning('Animation %d frames %s are not on the DACAI sprite sheets',
                            animation_id, missing)
            self._sprite_animations.pop(animation_id, None)
            return True
        previous = self._sprite_animations.pop(animation_id, None)
        if not enabled:
            return True
        frame = first_icon
        if not restart_from_first and previous is not None and previous['frame'] in frames:
            frame = previous['frame']
        # 0x28 counts the interval in 10 ms steps.
        self._sprite_animations[animation_id] = {
            'first': first_icon, 'last': last_icon, 'x': x, 'y': y,
            'period': max(.04, interval / 100), 'frame': frame, 'due': 0.0}
        self.poll_host_animations()
        return True

    def poll_host_animations(self, now=None):
        """Draw due animation frames; returns seconds until the next one (or None)."""
        if not self._sprite_animations or self._closed or self._sprites is None:
            return None
        now = time.monotonic() if now is None else now
        wait = None
        for animation_id, animation in list(self._sprite_animations.items()):
            if not (self._sprite_mask >> animation_id) & 1:
                continue
            if now >= animation['due']:
                if not self._draw_sprites((animation['frame'],),
                                          animation['x'], animation['y'], True):
                    self._sprite_animations.pop(animation_id, None)
                    continue
                last = animation['frame'] >= animation['last']
                animation['frame'] = animation['first'] if last else animation['frame'] + 1
                animation['due'] = now + animation['period']
            remaining = animation['due'] - now
            wait = remaining if wait is None else min(wait, remaining)
        self.update()
        return wait
