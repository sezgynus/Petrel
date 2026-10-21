"""Parse reader identification returned by the direct libnfc API."""
import re

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

