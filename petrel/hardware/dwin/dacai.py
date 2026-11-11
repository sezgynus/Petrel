"""DACAI panels that emulate the DWIN T5UIC1 protocol (e.g. Ender 3 Max Neo).

Creality ships some printers with a Guangzhou DACAI panel (Allwinner F1C100s,
microSD folder ``private`` instead of ``DWIN_SET``) whose firmware emulates
most of the T5UIC1 command set. The differences handled here were measured on
a Max Neo panel; see docs/dacai.md:

* SRAM JPEGs are drawn with 0x70 (0x24 is not implemented).
* 0x27 bit 7 is inverted: set = black transparent, clear = opaque.
* 0x33 stores the whole 32 KB SRAM as ``image/<id>.jpg`` and the loader
  requires FF D9 at the end of the file, so JPEGs are padded to 32 KB.
* Icon files cannot be written over UART. Icons are packed onto JPEG sprite
  sheets (petrel.artwork.sprites) and drawn with 0x25 + 0x27; animations
  (0x28) are stepped by the host.
* Data-Flash writes are acknowledged with a bare ``A5 'OK'``.
* 0x30 is clamped to 0..63; 0x38 re-clocks the host UART until power loss.
* Picture IDs above 15 are accepted.
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
    PICTURE_ID_MAX = 255
    BARE_FLASH_ACK = True
    # The firmware clamps 0x30 to 0..63 (63 = 100 %); 4 is the darkest usable level.
    BACKLIGHT_MAX = 63
    BACKLIGHT_MIN = 4

    def __init__(self, *args, host_baud=None, **kwargs):
        self.host_baud = configured_baud() if host_baud is None else host_baud
        self._sprites = None
        self._sprite_animations = {}
        self._sprite_mask = 0xFFFF
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Host link
    # ------------------------------------------------------------------

    def _after_handshake(self):
        if self.host_baud != DEFAULT_BAUD and isinstance(self.serial, serial.Serial):
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
                logging.info('DACAI host UART raised to %d baud', target)
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

    def copy_cache(self, cache_id, x0, y0, x1, y1, x, y, *,
                   background=False, restore=False, enhanced=True):
        # Bit 7 has the opposite meaning: set = black transparent.
        super().copy_cache(cache_id, x0, y0, x1, y1, x, y, background=not background,
                           restore=restore, enhanced=enhanced)

    def prepare_picture(self, data):
        return picture_payload(data)

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
        self.sync_sprites()
        self._assets_synced = True

    def sync_sprites(self, *, force=False):
        """Upload changed sheets; ``force`` repairs pictures removed by a microSD update."""
        from petrel.artwork import sprites
        self._sprite_animations.clear()
        try:
            current = sprites.load()
            if sprites.sync(self, force=force, sprites=current):
                self._cached_picture1 = None
            self._sprites = current.index
        except (OSError, T5UIC1TimeoutError):
            raise
        except Exception:
            # Without sheets, show_icon falls back to the panel's own icon files.
            logging.exception('Sprite sheet upload failed; using panel icon files')
            self._sprites = None

    def show_icon(self, library_id, icon_ids, x, y, *, background=True,
                  restore=False, enhanced=False):
        icons = (icon_ids,) if isinstance(icon_ids, int) else tuple(icon_ids)
        if icons and self._draw_sprites(library_id, icons, x, y, background):
            return
        super().show_icon(library_id, icon_ids, x, y, background=background,
                          restore=restore, enhanced=enhanced)

    def _draw_sprites(self, library_id, icons, x, y, background):
        """Copy icons from their sheets in a row; False leaves the call to 0x23."""
        from petrel.artwork.resources import ICON_LIBRARY_ID
        from petrel.artwork.sprites import FIRST_SLOT
        if self._sprites is None or library_id != ICON_LIBRARY_ID:
            return False
        entries = [self._sprites.get(icon) for icon in icons]
        if None in entries:
            return False
        for sheet, x0, y0, width, height in entries:
            self.ensure_cached_picture(FIRST_SLOT + sheet)
            self.copy_cache(1, x0, y0, x0 + width - 1, y0 + height - 1, x, y,
                            background=background, enhanced=False)
            x += width
        return True

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
        """Host-side replacement for 0x28 while icons come from sprite sheets."""
        from petrel.artwork.resources import ICON_LIBRARY_ID
        if self._sprites is None or library_id != ICON_LIBRARY_ID:
            return False
        if not 0 <= animation_id <= 15:
            raise ValueError('animation ID must be 0..15')
        frames = range(first_icon, last_icon + 1)
        if not frames or any(icon not in self._sprites for icon in frames):
            return False
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
                from petrel.artwork.resources import ICON_LIBRARY_ID
                if not self._draw_sprites(ICON_LIBRARY_ID, (animation['frame'],),
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
