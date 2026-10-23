"""Build and synchronize the managed JPEG icon library."""
from lcd_resources import ICON_BOOT_FIRST, ICON_BOOT_LAST
import hashlib
from functools import lru_cache
from io import BytesIO
import logging
from pathlib import Path
import re
import struct
import time
import zlib

from PIL import Image, JpegImagePlugin
from lcd_resources import ICON_LIBRARY_ID

BLOCK_SIZE = 32768
USABLE_SIZE = BLOCK_SIZE - 1
DIRECTORY_SIZE = 4096
SOURCE_DIRECTORY = Path(__file__).resolve().parent / 'assets/icons'
METADATA_ADDRESS = 0x0200
METADATA_SIZE = 512
# ID meaning changed: old metadata must not start the new boot range.
MAGIC = b'PETICO02'
MAX_BLOCKS = 16 - ICON_LIBRARY_ID
_ATTEMPTS = set()


def _best_fit_layout(records):
    """Fast valid baseline; allow overflow so optimization can try to rescue it."""
    layout = [[]]
    used = [DIRECTORY_SIZE]
    for record in records:
        size = len(record[3])
        fits = [i for i, end in enumerate(used) if USABLE_SIZE - end >= size]
        if fits:
            block = min(fits, key=lambda i: (USABLE_SIZE - used[i] - size, i))
        else:
            block = len(layout)
            layout.append([])
            used.append(0)
        layout[block].append(record)
        used[block] += size
    return layout


def _compact_layout(records, block_count):
    """Fill each earlier block with an exact bounded subset-sum search.

    Python integer bitsets represent reachable byte totals. The saved bitsets
    reconstruct a subset without reusing a record. This is exact for each
    individual block, not a globally optimal bin-packing proof.
    """
    remaining = list(records)
    layout = []
    for block in range(block_count - 1):
        capacity = USABLE_SIZE - (DIRECTORY_SIZE if block == 0 else 0)
        mask = (1 << (capacity + 1)) - 1
        reachable = 1
        history = []
        for position, record in enumerate(remaining):
            size = len(record[3])
            if size > capacity:
                continue
            before = reachable
            reachable |= (reachable << size) & mask
            history.append((position, before))
            if (reachable >> capacity) & 1:
                break
        target = reachable.bit_length() - 1
        chosen = set()
        for position, before in reversed(history):
            if not (before >> target) & 1:
                chosen.add(position)
                target -= len(remaining[position][3])
        layout.append([record for i, record in enumerate(remaining) if i in chosen])
        remaining = [record for i, record in enumerate(remaining) if i not in chosen]
    capacity = USABLE_SIZE - (DIRECTORY_SIZE if block_count == 1 else 0)
    if sum(len(record[3]) for record in remaining) > capacity:
        return None
    layout.append(remaining)
    return layout


def _layout_score(layout):
    free = [USABLE_SIZE - sum(len(record[3]) for record in block)
            - (DIRECTORY_SIZE if i == 0 else 0)
            for i, block in enumerate(layout)]
    # Never trade an extra Flash block for a larger hole.
    return len(layout), -max(free)


def pack_records(records):
    """Preserve JPEG bytes and IDs; consolidate free space deterministically."""
    records = sorted(records, key=lambda r: (-len(r[3]), r[0]))
    if not records:
        raise ValueError('Icon source directory is empty')
    seen = set()
    for index, width, height, payload in records:
        if index in seen or not 0 <= index <= 255:
            raise ValueError(f'Duplicate or invalid icon ID: {index}')
        seen.add(index)
        if not 0 < len(payload) <= USABLE_SIZE:
            raise ValueError(f'Icon {index} exceeds usable block capacity')
    if DIRECTORY_SIZE + sum(len(record[3]) for record in records) > MAX_BLOCKS * USABLE_SIZE:
        raise ValueError(f'Icons exceed reserved Picture Flash slots {ICON_LIBRARY_ID}..15')
    baseline = _best_fit_layout(records)
    layout = baseline
    total = DIRECTORY_SIZE + sum(len(record[3]) for record in records)
    minimum = (total + USABLE_SIZE - 1) // USABLE_SIZE
    # Adding a reserved slot must not make us consume it prematurely: best-fit
    # may need more blocks than an exact per-block subset layout does.
    for count in range(minimum, min(len(baseline), MAX_BLOCKS) + 1):
        candidate = _compact_layout(records, count)
        if candidate is not None:
            if _layout_score(candidate) < _layout_score(layout):
                layout = candidate
            break
    if len(layout) > MAX_BLOCKS:
        raise ValueError(f'Icons exceed reserved Picture Flash slots {ICON_LIBRARY_ID}..15')
    blocks = [bytearray(BLOCK_SIZE) for _ in layout]
    for block, items in enumerate(layout):
        start = DIRECTORY_SIZE if block == 0 else 0
        for index, width, height, payload in items:
            offset = block * BLOCK_SIZE + start
            blocks[block][start:start + len(payload)] = payload
            entry = struct.pack('>HHI', width, height, offset) + len(payload).to_bytes(3, 'big') + bytes(5)
            blocks[0][index * 16:(index + 1) * 16] = entry
            start += len(payload)
    return b''.join(blocks)


def build_library(directory=SOURCE_DIRECTORY):
    records = []
    for path in sorted(Path(directory).iterdir()):
        if not path.is_file() or path.suffix.lower() not in ('.jpg', '.jpeg'):
            continue
        match = re.fullmatch(r'(\d{1,3})(?:[-_].*)?', path.stem)
        if not match:
            raise ValueError(f'JPEG filename must start with icon ID: {path.name}')
        payload = path.read_bytes()
        with Image.open(BytesIO(payload)) as image:
            if image.format != 'JPEG' or image.info.get('progressive') or image.info.get('progression'):
                raise ValueError(f'Use baseline JPEG: {path.name}')
            if JpegImagePlugin.get_sampling(image) != 2:
                raise ValueError(f'Use baseline 4:2:0 JPEG for T5UIC1 icons: {path.name}')
            image.load()
            width, height = image.size
        records.append((int(match[1]), width, height, payload))
    return pack_records(records)


# Keep only the most recent packed library. Reconnects should check panel
# metadata instead of repeatedly JPEG-decoding and repacking unchanged icons.
_ORIGINAL_BUILD_LIBRARY = build_library


@lru_cache(maxsize=1)
def _cached_pack(directory, signature):
    return build_library(directory)


def _library_data(directory, force=False):
    if force or build_library is not _ORIGINAL_BUILD_LIBRARY:
        # Explicit maintenance requests and injected test builders must not
        # observe a cache from a previous revision of their sources.
        return build_library(directory)
    root = Path(directory).resolve()
    signature = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                      for p in sorted(root.iterdir()) if p.is_file()
                      and p.suffix.lower() in ('.jpg', '.jpeg'))
    return _cached_pack(root, signature)


def metadata(hashes):
    body = MAGIC + bytes((ICON_LIBRARY_ID, len(hashes)))
    body += b''.join(hashes) + bytes(32 * (MAX_BLOCKS - len(hashes)))
    body = body.ljust(METADATA_SIZE - 4, b'\x00')
    return body + zlib.crc32(body).to_bytes(4, 'big')


def parse_metadata(raw, *, library=ICON_LIBRARY_ID):
    if len(raw) != METADATA_SIZE or raw[:8] != MAGIC or raw[8] != library:
        return []
    if not 1 <= raw[9] <= 16 - library or int.from_bytes(raw[-4:], 'big') != zlib.crc32(raw[:-4]):
        return []
    return [raw[10 + i * 32:42 + i * 32] for i in range(raw[9])]


def sync_library(lcd, *, directory=SOURCE_DIRECTORY, force=False, automatic=True):
    data = _library_data(directory, force=force)
    blocks = [data[i:i + BLOCK_SIZE] for i in range(0, len(data), BLOCK_SIZE)]
    wanted = [hashlib.sha256(block).digest() for block in blocks]
    stored_metadata = lcd.read_flash(METADATA_ADDRESS, METADATA_SIZE)
    current = parse_metadata(stored_metadata)
    changed = [i for i, digest in enumerate(wanted)
               if force or i >= len(current) or current[i] != digest]
    if not changed:
        logging.info('Icon library: unchanged; no Flash writes')
        return False
    # A migrated library overlaps the old one. Stop every resident animation
    # before rewriting either directory or payload blocks.
    lcd.set_animation_mask(0)
    lcd.configure_animation(0, False, ICON_LIBRARY_ID, ICON_BOOT_FIRST, ICON_BOOT_LAST, 0, 320, 10)
    # Whenever any payload changes, commit the directory last, even if its
    # bytes happen to match. Its checkpoint denotes a completed upload.
    current = (current + [bytes(32)] * len(wanted))[:len(wanted)]
    current[0] = bytes(32)

    def checkpoint():
        nonlocal stored_metadata
        raw = metadata(current)
        if raw == stored_metadata:
            return
        lcd.write_flash(METADATA_ADDRESS, raw)
        if lcd.read_flash(METADATA_ADDRESS, METADATA_SIZE) != raw:
            raise RuntimeError('Icon metadata verification failed')
        stored_metadata = raw

    checkpoint()
    for index in [i for i in changed if i != 0] + [0]:
        slot = ICON_LIBRARY_ID + index
        key = (slot, wanted[index])
        if automatic and key in _ATTEMPTS:
            raise RuntimeError('Automatic icon rewrite blocked after an earlier failed attempt; restart or reload explicitly')
        logging.info('Icon library: uploading slot %d (%d/%d)', slot, index + 1, len(blocks))
        # Never send a write that includes SRAM address 0x7FFF. The copied
        # Flash byte is unused padding and no directory/JPEG references it.
        lcd.write_sram(0, blocks[index][:USABLE_SIZE])
        lcd.serial.flush()
        time.sleep(0.1)
        if automatic:
            _ATTEMPTS.add(key)
        lcd.store_sram_as_picture(slot, timeout=5)
        current[index] = wanted[index]
        checkpoint()
        _ATTEMPTS.discard(key)
    logging.info('Icon library: upload complete')
    return True
