#!/usr/bin/env python3
"""Re-upload Petrel's artwork to a DACAI panel.

Use it after the panel's microSD update removed the uploaded pictures: Petrel's
Data-Flash checkpoints survive such an update, so a normal start would skip
the upload. Stop Petrel first so only one process uses the UART:

    sudo systemctl stop Petrel.service
    ~/petrel-env/bin/python ~/Petrel/tools/dacai_artwork.py --serial-port /dev/ttyS0
    sudo systemctl start Petrel.service
"""
import argparse
import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--serial-port', default=os.environ.get('PETREL_SERIAL_PORT', '/dev/ttyS0'))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    from petrel.artwork import boot, shared
    from petrel.hardware.dwin.dacai import DacaiDriver
    lcd = DacaiDriver(args.serial_port)
    try:
        boot.sync(lcd, force=True)
        shared.sync(lcd, force=True)
        lcd.sync_sprites(force=True)
        uploaded = lcd._sprites is not None
        lcd.show_jpeg(0)
        lcd.update()
    finally:
        lcd.close()
    if not uploaded:
        print('Icon sprite sheets could not be uploaded; see the log above.')
        return 1
    print('DACAI artwork uploaded.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
