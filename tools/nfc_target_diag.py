#!/usr/bin/env python3
"""Enable or disable isolated upstream PN532 0x05 target diagnostics.

The marker and the library must be visible to the Petrel.service user.
Restart Petrel.service after a change; never switch a loaded CDLL live.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfc_target_experiment import (
    diagnostics_file, diagnostics_enabled, diagnostics_library_path,
    selected_profile, modedet_enabled, system_modedet_enabled,
)


def enable():
    if system_modedet_enabled():
        raise ValueError('Disable system ModeDetOff before enabling diagnostics')
    if modedet_enabled():
        raise ValueError('Disable PN532 ModeDetOff before enabling diagnostics')
    profile = selected_profile()
    if profile not in ('A', 'B'):
        raise ValueError('Select upstream libnfc Mode 0x05 profile A or B first')
    lib = diagnostics_library_path()  # Fail closed if build is incomplete.
    flag = diagnostics_file()
    flag.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix='.nfc-diag-', dir=flag.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('enabled-v1\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, flag)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return profile, lib


def disable():
    diagnostics_file().unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('enable', 'disable', 'status'))
    args = parser.parse_args()
    try:
        if args.command == 'enable':
            profile, lib = enable()
            print('PN532 diagnostic active for profile %s: %s' % (profile, lib))
        elif args.command == 'disable':
            disable()
            print('PN532 diagnostic disabled; ordinary library restored on restart')
        else:
            active = diagnostics_enabled()
            print('PN532 diagnostics: %s' % ('enabled' if active else 'disabled'))
            print('Mode profile: %s' % (selected_profile() or 'default'))
            if active:
                print('Library: %s' % diagnostics_library_path())
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print('Restart Petrel.service for the selection to take effect.')


if __name__ == '__main__':
    main()
