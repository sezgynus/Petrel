"""Petrel's icon library as JPEG sprite sheets in picture slots (DACAI panels).

DACAI panels only read icons from their own icon files, which cannot be written
over UART. They do store full JPEG pictures with 0x33, so the icons are packed
onto portrait sheets, uploaded once into picture slots ``FIRST_SLOT``.. and
drawn by copying from virtual area 1 (0x25 + 0x27). No microSD card is needed.
"""
from functools import lru_cache
import hashlib
from io import BytesIO
import logging
from pathlib import Path
import re
import time
import zlib

from PIL import Image

from petrel.artwork.icon_library import SOURCE_DIRECTORY
from petrel.artwork.resources import (
    ICON_NFC_CARD_FIRST, ICON_NFC_CARD_LAST, ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST,
    ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST)

# Sheets are laid out like virtual area 1 is addressed (portrait).
SHEET_WIDTH, SHEET_HEIGHT = 272, 480
# 0x33 accepts picture IDs above 15 on DACAI; keep 0..15 for boot/shared/stock.
FIRST_SLOT = 16
MAX_SHEETS = 16
# JPEG 4:2:0 codes 16x16 blocks: icons on a 16 px grid never share a block,
# so neighbouring icons cannot bleed colour into each other's black backing.
CELL = 16
# DACAI pads pictures to 32 KB with a 4-byte COM segment header.
MAX_JPEG = 0x8000 - 4
METADATA_ADDRESS = 0x0600
METADATA_SIZE = 576
MAGIC = b'PETSPR01'
# Large NFC approach frames: DACAI has no auxiliary UART for an NFC reader.
SKIPPED_IDS = frozenset(
    list(range(ICON_NFC_CARD_FIRST, ICON_NFC_CARD_LAST + 1))
    + list(range(ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST + 1))
    + list(range(ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST + 1)))
_ATTEMPTS = set()


class SpriteSet:
    """Encoded sheets plus icon ID -> (sheet, x, y, width, height)."""

    def __init__(self, payloads, index):
        self.payloads = tuple(payloads)
        self.index = dict(index)
        self.digests = tuple(hashlib.sha256(p).digest() for p in self.payloads)


def _cells(pixels):
    return -(-pixels // CELL) * CELL


def _fit(sheet, width, height):
    for shelf in sheet['shelves']:
        if height <= shelf[1] and shelf[2] + width <= SHEET_WIDTH:
            x = shelf[2]
            shelf[2] += width
            return x, shelf[0]
    if sheet['height'] + height <= SHEET_HEIGHT and width <= SHEET_WIDTH:
        y = sheet['height']
        sheet['shelves'].append([y, height, width])
        sheet['height'] += height
        return 0, y
    return None


def pack(sizes):
    """Shelf-pack {id: (w, h)} on the 16 px grid; returns (sheet_count, {id: (sheet, x, y)})."""
    order = sorted(sizes, key=lambda i: (-_cells(sizes[i][1]), -_cells(sizes[i][0]), i))
    sheets, placement = [], {}
    for index in order:
        width, height = (_cells(v) for v in sizes[index])
        if width > SHEET_WIDTH or height > SHEET_HEIGHT:
            raise ValueError(f'Icon {index} is larger than a sprite sheet')
        for number, sheet in enumerate(sheets):
            spot = _fit(sheet, width, height)
            if spot is not None:
                break
        else:
            sheets.append({'shelves': [], 'height': 0})
            number, spot = len(sheets) - 1, _fit(sheets[-1], width, height)
        placement[index] = (number, spot[0], spot[1])
    if len(sheets) > MAX_SHEETS:
        raise ValueError(f'Icons need {len(sheets)} sprite sheets (max {MAX_SHEETS})')
    return len(sheets), placement


def encode(sheet):
    """Best baseline 4:2:0 JPEG quality that still fits one DACAI picture."""
    stored = sheet.rotate(90, expand=True)  # pictures are stored landscape
    low, high, best = 20, 95, None
    while low <= high:
        quality = (low + high) // 2
        buffer = BytesIO()
        stored.save(buffer, 'JPEG', quality=quality, subsampling=2, progressive=False)
        if len(buffer.getvalue()) <= MAX_JPEG:
            best, low = buffer.getvalue(), quality + 1
        else:
            high = quality - 1
    if best is None:
        raise ValueError('Sprite sheet does not fit one DACAI picture')
    return best


def build(directory=SOURCE_DIRECTORY):
    images = {}
    for path in sorted(Path(directory).iterdir()):
        if not path.is_file() or path.suffix.lower() not in ('.jpg', '.jpeg'):
            continue
        match = re.fullmatch(r'(\d{1,3})(?:[-_].*)?', path.stem)
        if not match or int(match[1]) in SKIPPED_IDS:
            continue
        with Image.open(path) as image:
            images[int(match[1])] = image.convert('RGB')
    if not images:
        raise ValueError('Icon source directory is empty')
    count, placement = pack({i: image.size for i, image in images.items()})
    sheets = [Image.new('RGB', (SHEET_WIDTH, SHEET_HEIGHT)) for _ in range(count)]
    index = {}
    for icon, (number, x, y) in placement.items():
        image = images[icon]
        sheets[number].paste(image, (x, y))
        index[icon] = (number, x, y) + image.size
    return SpriteSet([encode(sheet) for sheet in sheets], index)


@lru_cache(maxsize=1)
def _cached(directory, signature):
    return build(directory)


def load(directory=SOURCE_DIRECTORY):
    root = Path(directory).resolve()
    signature = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                      for p in sorted(root.iterdir()) if p.is_file())
    return _cached(root, signature)


def metadata(digests):
    body = MAGIC + bytes((FIRST_SLOT, len(digests))) + b''.join(digests)
    body = body.ljust(METADATA_SIZE - 4, b'\x00')
    return body + zlib.crc32(body).to_bytes(4, 'big')


def parse_metadata(raw):
    if (len(raw) != METADATA_SIZE or raw[:8] != MAGIC or raw[8] != FIRST_SLOT
            or not 1 <= raw[9] <= MAX_SHEETS
            or int.from_bytes(raw[-4:], 'big') != zlib.crc32(raw[:-4])):
        return []
    return [bytes(raw[10 + i * 32:42 + i * 32]) for i in range(raw[9])]


def resident(lcd, sprites=None):
    """True when every sheet of ``sprites`` is already stored on the panel."""
    sprites = sprites or load()
    return parse_metadata(lcd.read_flash(METADATA_ADDRESS, METADATA_SIZE)) == list(sprites.digests)


def sync(lcd, *, force=False, sprites=None):
    """Upload changed sheets; metadata is committed only after the pictures."""
    sprites = sprites or load()
    wanted = list(sprites.digests)
    stored = lcd.read_flash(METADATA_ADDRESS, METADATA_SIZE)
    current = parse_metadata(stored)
    changed = [i for i, digest in enumerate(wanted)
               if force or i >= len(current) or current[i] != digest]
    if not changed:
        logging.info('Sprite sheets: unchanged; no picture writes')
        return False
    key = tuple(wanted)
    if key in _ATTEMPTS and not force:
        raise RuntimeError('Sprite upload already failed; restart to retry')
    _ATTEMPTS.add(key)

    def commit(digests):
        raw = metadata(digests)
        lcd.write_flash(METADATA_ADDRESS, raw)
        if lcd.read_flash(METADATA_ADDRESS, METADATA_SIZE) != raw:
            raise RuntimeError('Sprite metadata verification failed')

    pending = (current + [bytes(32)] * len(wanted))[:len(wanted)]
    for i in changed:
        pending[i] = bytes(32)
    if parse_metadata(stored) != pending:
        commit(pending)
    for i in changed:
        logging.info('Sprite sheets: uploading picture %d (%d/%d)',
                     FIRST_SLOT + i, changed.index(i) + 1, len(changed))
        lcd.write_sram(0, lcd.prepare_picture(sprites.payloads[i]))
        lcd.serial.flush()
        time.sleep(.1)
        lcd.store_sram_as_picture(FIRST_SLOT + i, timeout=5)
        pending[i] = wanted[i]
    commit(pending)
    _ATTEMPTS.discard(key)
    logging.info('Sprite sheets: upload complete (%d sheets)', len(wanted))
    return True
