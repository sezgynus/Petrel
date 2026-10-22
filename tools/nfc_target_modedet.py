#!/usr/bin/env python3
"""Switch isolated PN532 CIU_Mode.ModeDetOff experiment on/off.

Test with profile A (Mode=0x05) or C (Mode=0x04), both ATQA=00 04. The ordinary A/C build
and system libnfc are never overwritten. Restart Petrel.service after each
change because the native CDLL is process-cached.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfc_target_experiment import (
    modedet_file, modedet_enabled, modedet_library_path,
    selected_profile, diagnostics_enabled,
)


def enable():
    if diagnostics_enabled():
        raise ValueError('Disable PN532 diagnostics before enabling ModeDetOff')
    if selected_profile() not in ('A', 'C'):
        raise ValueError('Select profile A or C before enabling PN532 ModeDetOff')
    library = modedet_library_path()
    target = modedet_file()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.nfc-modedet-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write('enabled-v1\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return library


def disable():
    modedet_file().unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('enable', 'disable', 'status'))
    args = parser.parse_args()
    try:
        if args.command == 'enable':
            print('PN532 ModeDetOff enabled: ' + enable())
        elif args.command == 'disable':
            disable()
            print('PN532 ModeDetOff disabled; ordinary selected A/C library resumes on restart.')
        else:
            active = modedet_enabled()
            print('PN532 ModeDetOff: %s' % ('enabled' if active else 'disabled'))
            print('Profile: %s' % (selected_profile() or 'default'))
            if active:
                print('Library: ' + modedet_library_path())
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print('Restart Petrel.service for the change to take effect.')


if __name__ == '__main__':
    main()
