#!/usr/bin/env python3
"""Select one of four physical PN532 target-mode/ATQA experiments.

Switch profiles only when no NFC share is active. Restart Petrel.service after
selection: the libnfc CDLL is cached for the entire Petrel process.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile
import sys

# Running `python3 tools/nfc_target_ab.py` must resolve the repository module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfc_target_experiment import (
    PROFILES, config_file, library_for_mode, selected_profile, diagnostics_enabled,
    modedet_enabled,
)


def select(profile):
    mode, atqa = PROFILES[profile]
    if modedet_enabled() and profile != 'C':
        raise ValueError('Disable PN532 ModeDetOff before selecting a different profile')
    if diagnostics_enabled() and mode != 0x05:
        raise ValueError('Disable PN532 diagnostics before selecting mode 0x04')
    library_for_mode(mode)  # Do not allow a silent fallback to system libnfc.
    target = config_file()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.nfc-target-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'profile': profile}, f)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return mode, atqa


def reset():
    if modedet_enabled():
        raise ValueError('Disable PN532 ModeDetOff before resetting the profile')
    config_file().unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    test = commands.add_parser('select', help='Select the physical test profile')
    test.add_argument('profile', choices=tuple(PROFILES))
    commands.add_parser('status', help='Show selection, without using NFC hardware')
    commands.add_parser('reset', help='Restore previously working 0x04/00 08')
    args = parser.parse_args()
    if args.command == 'select':
        mode, atqa = select(args.profile)
        print('Selected %s: Mode 0x%02X / ATQA %02X %02X' %
              (args.profile, mode, *atqa))
    elif args.command == 'reset':
        reset()
        print('Experimental override cleared: default Mode 0x04 / ATQA 00 08')
    else:
        name = selected_profile()
        mode, atqa = PROFILES[name] if name else PROFILES['D']
        print('Profile %s: Mode 0x%02X / ATQA %02X %02X' %
              (name or 'default D', mode, *atqa))
        if name is not None:
            print('Library: %s' % library_for_mode(mode))
    print('Restart Petrel.service for changes to take effect.')


if __name__ == '__main__':
    main()
