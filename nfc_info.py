"""One-shot libnfc reader identification; no card polling or raw UART protocol."""
import os
import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_DEVICE = 'pn532_uart:/dev/ttyDWIN0:115200'


def parse_info(output):
    chip = re.search(r'^chip:\s*(\S+)\s+v([\d.]+)\s*$', output, re.MULTILINE)
    library = re.search(r'uses libnfc\s+(\S+)', output)
    if not chip:
        return {'status': 'Unavailable'}
    modes = re.search(r'^init[i]?ator mode modulations:\s*(.*)$', output, re.MULTILINE)
    modes = modes.group(1) if modes else ''
    return {
        'status': 'Connected', 'model': chip[1], 'firmware': chip[2],
        'library': library[1] if library else 'Unavailable',
        # PN532 firmware identification exposes no board HW revision.
        'hardware': 'Not reported',
        'iso_a': 'Yes' if 'ISO/IEC 14443A' in modes else 'Unknown',
        'iso_b': 'Yes' if 'ISO/IEC 14443B' in modes else 'Unknown',
        'felica': 'Yes' if 'FeliCa' in modes else 'Unknown',
    }


def read_nfc_info():
    tool = shutil.which('nfc-scan-device')
    if tool is None:
        return {'status': 'libnfc missing'}
    device = os.environ.get('PETREL_NFC_DEVICE', DEFAULT_DEVICE)
    # Explicit device only. Never probe the printer MCU or other serial ports.
    if device == DEFAULT_DEVICE and not Path('/dev/ttyDWIN0').exists():
        return {'status': 'Unavailable'}
    env = dict(os.environ, LC_ALL='C', LIBNFC_DEVICE=device,
               LIBNFC_AUTO_SCAN='false', LIBNFC_INTRUSIVE_SCAN='false',
               LIBNFC_LOG_LEVEL='0')
    try:
        result = subprocess.run([tool, '-v'], env=env, capture_output=True,
                                text=True, errors='replace', timeout=4, check=False)
    except subprocess.TimeoutExpired:
        return {'status': 'Timed out'}
    except OSError:
        return {'status': 'Unavailable'}
    if result.returncode:
        return {'status': 'Unavailable'}
    return parse_info(result.stdout)
