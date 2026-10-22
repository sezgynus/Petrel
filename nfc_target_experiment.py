"""Controlled PN532 target-mode/ATQA matrix for physical acceptance tests.

The normal, already-tested behavior is mode 0x04 + ATQA 00 08.
Only an explicit, private profile file changes that behavior. A profile
must never silently fall back to a different library build.
"""
import json
import os
from pathlib import Path

# (PN532 TgInitAsTarget Mode, ctypes nfc_iso14443a_info.atqa)
PROFILES = {
    'A': (0x05, (0x00, 0x04)),  # Upstream mode, original ATQA
    'B': (0x05, (0x00, 0x08)),  # Upstream mode, newer ATQA
    'C': (0x04, (0x00, 0x04)),  # PICC-only mode, original ATQA
    'D': (0x04, (0x00, 0x08)),  # Current working configuration
}
DEFAULT_ATQA = (0x00, 0x08)


def config_file():
    return Path(os.environ.get('XDG_CONFIG_HOME') or
                (Path.home() / '.config')) / 'Petrel' / 'nfc-target-experiment.json'


def data_home():
    return Path(os.environ.get('XDG_DATA_HOME') or
                (Path.home() / '.local' / 'share')) / 'Petrel'


def library_root(mode):
    if mode == 0x04:
        return data_home() / 'libnfc-pn532-picc'
    if mode == 0x05:
        return data_home() / 'libnfc-pn532-mode05'
    raise ValueError('Unsupported PN532 target mode')


def library_for_mode(mode):
    root = library_root(mode)
    lib, marker = root / 'lib' / 'libnfc.so.6', root / '.petrel-pn532-picc'
    # A checked marker protects against a partially installed library.
    if not (lib.is_file() and marker.is_file()):
        raise OSError('PN532 mode 0x%02X build not installed: %s' % (mode, root))
    if 'mode=0x%02X' % mode not in marker.read_text():
        raise OSError('PN532 mode 0x%02X marker does not match library' % mode)
    return str(lib)


def selected_profile():
    path = config_file()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('Invalid NFC target experiment file') from error
    if not isinstance(raw, dict) or set(raw) != {'profile'}:
        raise ValueError('NFC target experiment must contain only profile')
    profile = raw['profile']
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError('Unknown NFC target experiment profile')
    return profile


def target_atqa():
    profile = selected_profile()
    return DEFAULT_ATQA if profile is None else PROFILES[profile][1]
