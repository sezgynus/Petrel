"""Synchronize Petrel's boot JPEG directly into panel picture slot 0."""
import hashlib
from io import BytesIO
import logging
from pathlib import Path
import time

from PIL import Image

SOURCE = Path(__file__).resolve().parent / 'assets/petrel_bootsplash.jpg'
ADDRESS = 0x0120
SIZE = 40
MAGIC = b'PETBOOT1'
_attempts = set()


def sync(lcd, source=SOURCE, *, force=False):
    data = Path(source).read_bytes()
    if len(data) > 32767:
        raise ValueError('Boot JPEG must fit before SRAM address 0x7FFF')
    with Image.open(BytesIO(data)) as image:
        if image.format != 'JPEG' or image.size != (480, 272) or image.info.get('progressive'):
            raise ValueError('Boot artwork must be a baseline 480x272 JPEG')
        image.load()
    record = MAGIC + hashlib.sha256(data).digest()
    if lcd.read_flash(ADDRESS, SIZE) == record and not force:
        return False
    if record in _attempts:
        raise RuntimeError('Boot Flash write already failed; restart to retry')
    if force:
        # A stock SD restore can replace slot 0 but leave our checkpoint.
        # Invalidate before writing so an interrupted repair cannot look current.
        invalid = bytes(SIZE)
        lcd.write_flash(ADDRESS, invalid)
        if lcd.read_flash(ADDRESS, SIZE) != invalid:
            raise RuntimeError('Boot artwork metadata invalidation failed')
    logging.info('Uploading Petrel boot artwork to picture slot 0')
    lcd.write_sram(0, data)
    lcd.serial.flush()
    time.sleep(.1)
    _attempts.add(record)
    lcd.store_sram_as_picture(0, timeout=5)
    # Commit only after the panel acknowledges the picture write.
    lcd.write_flash(ADDRESS, record)
    if lcd.read_flash(ADDRESS, SIZE) != record:
        raise RuntimeError('Boot artwork metadata verification failed')
    _attempts.discard(record)
    return True
