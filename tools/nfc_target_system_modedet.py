#!/usr/bin/env python3
"""Opt-in PN532 ModeDetOff using unmodified system libnfc's exported symbol.

No libnfc source download, build or custom .so is needed. Enable only after
selecting target profile A; an NFC service restart reloads the CDLL.
"""
import argparse
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfc_target_experiment import (
    system_modedet_file, system_modedet_enabled, selected_profile,
    modedet_enabled, diagnostics_enabled,
)


def probe_library():
    name = C.util.find_library('nfc')
    if not name:
        raise OSError('System libnfc6 not installed')
    try:
        lib = C.CDLL(name)
        write = lib.pn53x_write_register
        write.restype = C.c_int
        write.argtypes = [C.c_void_p, C.c_uint16, C.c_uint8, C.c_uint8]
        version = lib.nfc_version
        version.restype = C.c_char_p
        version.argtypes = []
        release = version().decode('ascii', 'replace')
    except (OSError, AttributeError) as error:
        raise OSError('System libnfc lacks required PN53x register ABI: %s' % error) from error
    return name, release


def enable():
    if selected_profile() != 'A':
        raise ValueError('Select target profile A before enabling system register experiment')
    if modedet_enabled() or diagnostics_enabled():
        raise ValueError('Disable private PN532 ModeDetOff/diagnostics first')
    name, release = probe_library()
    target = system_modedet_file()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.nfc-system-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write('enabled-v1\n')
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return name, release


def disable():
    system_modedet_file().unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('enable', 'disable', 'status', 'probe'))
    args = parser.parse_args()
    try:
        if args.command == 'enable':
            name, release = enable()
            print('System ModeDetOff experiment enabled: %s (libnfc %s)' % (name, release))
        elif args.command == 'disable':
            disable()
            print('System ModeDetOff experiment disabled')
        elif args.command == 'probe':
            name, release = probe_library()
            print('System libnfc: %s, version=%s, pn53x_write_register exported' % (name, release))
        else:
            print('System ModeDetOff: %s' % ('enabled' if system_modedet_enabled() else 'disabled'))
            print('Profile: %s' % (selected_profile() or 'default'))
            if system_modedet_enabled():
                name, release = probe_library()
                print('Library: %s (%s)' % (name, release))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.command in ('enable', 'disable'):
        print('Restart Petrel.service to apply the change.')


if __name__ == '__main__':
    main()
