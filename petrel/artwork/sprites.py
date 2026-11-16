"""Petrel's icon library as JPEG sprite sheets in picture slots (DACAI panels).

DACAI panels only read icons from their own icon files, which cannot be written
over UART. They do store full JPEG pictures with 0x33, so the icons are packed
onto portrait sheets, uploaded once into picture slots ``FIRST_SLOT``.. and
drawn by copying from virtual area 1 (0x25 + 0x27). No microSD card is needed.

Every icon is drawn from one or more pieces ``(sheet, x, y, width, height, dx,
dy)``: a piece copies ``width`` x ``height`` pixels from ``(x, y)`` on its sheet
to ``(dx, dy)`` inside the icon. Most icons are one full piece. The large NFC
animation frames (160x160) differ from each other only around the moving card
and the waves, so every later frame is drawn as the most similar earlier frame
of its sequence plus one patch. That keeps all NFC artwork on a few sheets
instead of nine more.
"""
from functools import lru_cache
import hashlib
from io import BytesIO
import logging
from pathlib import Path
import re
import time
import zlib

from PIL import Image, ImageChops

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
# Animation sequences stored as first frame + per-frame patches.
DELTA_SEQUENCES = ((ICON_NFC_CARD_FIRST, ICON_NFC_CARD_LAST),
                   (ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST),
                   (ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST))
# A pixel belongs to a patch when any channel differs by more than this from
# the first frame (the sources are JPEGs, so tiny differences are noise).
DELTA_THRESHOLD = 8
_ATTEMPTS = set()


class SpriteSet:
    """Encoded sheets plus icon ID -> pieces ``((sheet, x, y, w, h, dx, dy), ...)``."""

    def __init__(self, payloads, index):
        self.payloads = tuple(payloads)
        self.index = dict(index)
        self.digests = tuple(hashlib.sha256(p).digest() for p in self.payloads)


def _cells(pixels):
    return -(-pixels // CELL) * CELL


def _fit(sheet, width, height):
    """Lowest, then leftmost free spot for whole cells; ``sheet`` is a list of row bitmasks."""
    columns, rows = width // CELL, height // CELL
    mask = (1 << columns) - 1
    for y in range(len(sheet) - rows + 1):
        for x in range(SHEET_WIDTH // CELL - columns + 1):
            if not any(sheet[row] & (mask << x) for row in range(y, y + rows)):
                for row in range(y, y + rows):
                    sheet[row] |= mask << x
                return x * CELL, y * CELL
    return None


def pack(sizes, groups=()):
    """Pack {id: (w, h)} on the 16 px grid; returns (sheet_count, {id: (sheet, x, y)}).

    Largest first, each at the lowest free spot of the first sheet it fits on.

    Each group (a collection of ids) starts on a sheet of its own, so an
    animation drawn from several pieces does not switch sheets between
    frames; the remaining ids fill the free space of all sheets.
    """
    def order(ids):
        return sorted(ids, key=lambda i: (-_cells(sizes[i][1]), -_cells(sizes[i][0]), i))

    sheets, placement = [], {}

    def place(index, candidates):
        width, height = (_cells(v) for v in sizes[index])
        if width > SHEET_WIDTH or height > SHEET_HEIGHT:
            raise ValueError(f'Icon {index} is larger than a sprite sheet')
        for number in candidates:
            spot = _fit(sheets[number], width, height)
            if spot is not None:
                break
        else:
            sheets.append([0] * (SHEET_HEIGHT // CELL))
            number, spot = len(sheets) - 1, _fit(sheets[-1], width, height)
        placement[index] = (number, spot[0], spot[1])

    grouped = set()
    for group in groups:
        members = [i for i in group if i in sizes]
        grouped.update(members)
        # Prefer an order that fits the whole group on one sheet.
        for key in ((lambda i: (-_cells(sizes[i][0]), -_cells(sizes[i][1]), i)),
                    (lambda i: (-_cells(sizes[i][0]) * _cells(sizes[i][1]), i))):
            trial = [0] * (SHEET_HEIGHT // CELL)
            spots = [(i, _fit(trial, *(_cells(v) for v in sizes[i]))) for i in sorted(members, key=key)]
            if all(spot for _, spot in spots):
                sheets.append(trial)
                placement.update((i, (len(sheets) - 1,) + spot) for i, spot in spots)
                break
        else:
            start = len(sheets)
            for index in order(members):
                place(index, range(start, len(sheets)))
    for index in order(i for i in sizes if i not in grouped):
        place(index, range(len(sheets)))
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


def _delta_patch(base, frame):
    """Patch of ``frame`` over ``base``: (stored box, drawn box), or None if equal.

    The stored box is the changed region plus a 1 px margin, widened to the
    16 px JPEG grid of the frame. Placed on the grid of a sheet, every JPEG
    block of the patch holds patch pixels only. Chroma upsampling still blends
    the outermost pixel row with the sheet neighbour, so the drawn box leaves
    out that row wherever it is margin (the base frame already shows it).
    """
    difference = ImageChops.difference(frame, base).split()
    changed = ImageChops.lighter(ImageChops.lighter(difference[0], difference[1]), difference[2])
    box = changed.point([255 if v > DELTA_THRESHOLD else 0 for v in range(256)]).getbbox()
    if box is None:
        return None
    width, height = frame.size
    x0, y0 = max(0, box[0] - 1) // CELL * CELL, max(0, box[1] - 1) // CELL * CELL
    x1, y1 = min(width, _cells(box[2] + 1)), min(height, _cells(box[3] + 1))
    drawn = (x0 + (x0 > 0), y0 + (y0 > 0), x1 - (x1 < width), y1 - (y1 < height))
    return (x0, y0, x1, y1), drawn


def _grid_padded(image):
    """``image`` extended to whole 16 px cells by repeating its last column/row.

    The padding fills the JPEG blocks at the right and bottom edge, so the
    encoder does not blend the icon border with the black sheet background.
    """
    width, height = image.size
    padded = Image.new('RGB', (_cells(width), _cells(height)))
    padded.paste(image, (0, 0))
    if padded.width > width:
        padded.paste(image.crop((width - 1, 0, width, height)).resize((padded.width - width, height)),
                     (width, 0))
    if padded.height > height:
        padded.paste(padded.crop((0, height - 1, padded.width, height)).resize(
            (padded.width, padded.height - height)), (0, height))
    return padded


def _compose(crops, pieces, size):
    image = Image.new('RGB', size)
    for key, box, position in pieces:
        image.paste(crops[key].crop(box), position)
    return image


def _patched_layout(images, crops, layout, first, icon):
    """Pieces for animation frame ``icon``: an earlier frame of its sequence plus one patch.

    The earlier frame that needs the smallest patch wins, as long as the
    composed frame stays within DELTA_THRESHOLD of the source everywhere (small
    differences outside a patch must not add up along a chain of frames).
    Stores the chosen patch in ``crops``.
    """
    frame = images[icon]
    best = None
    for reference in range(first, icon):
        if reference not in layout or images.get(reference) is None \
                or images[reference].size != frame.size:
            continue
        patch = _delta_patch(images[reference], frame)
        pieces = list(layout[reference])
        cells = 0
        if patch is not None:
            stored, drawn = patch
            cells = (stored[2] - stored[0]) * (stored[3] - stored[1]) // (CELL * CELL)
            inner = (drawn[0] - stored[0], drawn[1] - stored[1],
                     drawn[2] - stored[0], drawn[3] - stored[1])
            pieces.append(((icon, 1), inner, drawn[:2]))
        rank = (cells, len(pieces), reference)
        if best is not None and rank >= best[0]:
            continue
        trial = dict(crops)
        if patch is not None:
            trial[(icon, 1)] = frame.crop(stored)
        error = ImageChops.difference(_compose(trial, pieces, frame.size), frame).getextrema()
        if max(high for _, high in error) <= DELTA_THRESHOLD:
            best = rank, pieces, patch and frame.crop(stored)
    _, pieces, crop = best
    if crop is not None:
        crops[(icon, 1)] = crop
    return pieces


def build(directory=SOURCE_DIRECTORY):
    images = {}
    for path in sorted(Path(directory).iterdir()):
        if not path.is_file() or path.suffix.lower() not in ('.jpg', '.jpeg'):
            continue
        match = re.fullmatch(r'(\d{1,3})(?:[-_].*)?', path.stem)
        if not match:
            continue
        with Image.open(path) as image:
            images[int(match[1])] = image.convert('RGB')
    if not images:
        raise ValueError('Icon source directory is empty')
    # Pieces to pack: (icon, 0) is a full icon, (icon, 1) a patch over its base.
    # layout: icon -> [(piece, drawn box inside the piece, position in the icon)]
    crops, layout = {}, {}
    # Pixel-identical icons (repeated animation frames) are stored once.
    first_of, same = {}, {}
    for icon in sorted(images):
        key = (images[icon].size, images[icon].tobytes())
        if key in first_of:
            same[icon] = first_of[key]
        else:
            first_of[key] = icon
    for icon, image in images.items():
        if icon in same:
            continue
        crops[(icon, 0)] = image
        layout[icon] = [((icon, 0), (0, 0) + image.size, (0, 0))]
    for first, last in DELTA_SEQUENCES:
        base = images.get(first)
        if base is None or first in same:
            continue
        for icon in range(first + 1, last + 1):
            frame = images.get(icon)
            if frame is None or frame.size != base.size:
                continue
            if icon in same:
                if same[icon] in layout:
                    layout[icon] = layout[same[icon]]
                continue
            del crops[(icon, 0)]
            layout[icon] = _patched_layout(images, crops, layout, first, icon)
    for icon, original in same.items():
        layout.setdefault(icon, layout[original])
    groups = [{(first, 0)} | {(icon, 1) for icon in range(first + 1, last + 1)}
              for first, last in DELTA_SEQUENCES]
    count, placement = pack({key: image.size for key, image in crops.items()}, groups)
    sheets = [Image.new('RGB', (SHEET_WIDTH, SHEET_HEIGHT)) for _ in range(count)]
    for key, (number, x, y) in placement.items():
        sheets[number].paste(_grid_padded(crops[key]), (x, y))
    index = {icon: tuple((placement[key][0], placement[key][1] + box[0], placement[key][2] + box[1],
                          box[2] - box[0], box[3] - box[1]) + position
                         for key, box, position in pieces)
             for icon, pieces in layout.items()}
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
