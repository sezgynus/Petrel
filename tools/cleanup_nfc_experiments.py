#!/usr/bin/env python3
"""Remove obsolete PN532 target experiments from the current service user's Pi.

Use --apply only after deploying the production system-libnfc target code.
Preserves the apt libnfc6 package, NFC reader settings, Petrel data and services.
"""
import argparse
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import shutil
import sys

# Direct invocation (python3 tools/cleanup_nfc_experiments.py) places only the
# tools directory on sys.path. Resolve the Petrel root for libnfc_api imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PRIVATE_BUILD_DIRS = (
    'libnfc-pn532-picc',
    'libnfc-pn532-mode05',
    'libnfc-pn532-diagnostics',
    'libnfc-pn532-modedet',
    'libnfc-pn532-modedet05',
)
EXPERIMENT_CONFIG = (
    'nfc-target-experiment.json',
    'nfc-target-diagnostics.enabled',
    'nfc-target-modedet.enabled',
    'nfc-target-system-modedet.enabled',
)
TEMP_CONFIG_PREFIXES = (
    '.nfc-target-', '.nfc-diag-', '.nfc-modedet-', '.nfc-system-',
)
TEMP_BUILD_PREFIX = '.pn532-picc-build.'


def paths(data, config):
    paths_to_remove = [data / name for name in PRIVATE_BUILD_DIRS]
    paths_to_remove += [config / name for name in EXPERIMENT_CONFIG]
    if data.is_dir():
        paths_to_remove += [
            p for p in data.iterdir() if p.name.startswith(TEMP_BUILD_PREFIX)
        ]
    if config.is_dir():
        paths_to_remove += [
            p for p in config.iterdir()
            if any(p.name.startswith(prefix) for prefix in TEMP_CONFIG_PREFIXES)
        ]
    return tuple(p for p in paths_to_remove if p.exists() or p.is_symlink())


def validate_production():
    from petrel.features.nfc.libnfc import (
        PN532_TARGET_ATQA, PN532_MODEDET_ADDRESS, PN532_MODEDET_MASK,
        library_path, bind_pn532_register,
    )
    if (PN532_TARGET_ATQA, PN532_MODEDET_ADDRESS, PN532_MODEDET_MASK) != (
            (0, 4), 0x6301, 0x04):
        raise RuntimeError('Production PN532 configuration is not active')
    library = library_path()
    if not library or library != C.util.find_library('nfc'):
        raise RuntimeError('Stock system libnfc is not selected')
    bind_pn532_register(C.CDLL(library))


def cleanup(data, config, apply=False):
    if data.is_symlink() or config.is_symlink():
        raise RuntimeError('Refusing cleanup through a symlinked Petrel directory')
    validate_production()
    items = paths(data, config)
    for p in items:
        print(('Removing: ' if apply else 'Would remove: ') + str(p))
        if not apply:
            continue
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    print('Obsolete PN532 experiments: %d path(s) %s.' % (
        len(items), 'removed' if apply else 'found (dry run)'))
    return len(items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Delete listed experiment paths (default: dry run)')
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as the Petrel service user, not root')
    data = Path(os.environ.get('XDG_DATA_HOME') or
                (Path.home() / '.local' / 'share')) / 'Petrel'
    config = Path(os.environ.get('XDG_CONFIG_HOME') or
                  (Path.home() / '.config')) / 'Petrel'
    try:
        cleanup(data, config, apply=args.apply)
    except (OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
