#!/usr/bin/env python3
"""Add new opt-in defaults without resetting an existing installation."""
from pathlib import Path
import re
import sys


def ensure_emulator_default(path):
    path = Path(path)
    text = path.read_text()
    if re.search(r'^\s*PETREL_EMULATOR=', text, re.MULTILINE):
        return False
    with path.open('a') as stream:
        stream.write(('' if not text or text.endswith('\n') else '\n') + 'PETREL_EMULATOR=0\n')
    return True


def ensure_aux_uart_default(path):
    path = Path(path)
    text = path.read_text()
    if re.search(r'^\s*PETREL_AUX_UART=', text, re.MULTILINE):
        return False
    with path.open('a') as stream:
        stream.write(('' if not text or text.endswith('\n') else '\n') + 'PETREL_AUX_UART=0\n')
    return True


def ensure_nfc_default(path):
    path = Path(path)
    text = path.read_text()
    if re.search(r'^\s*PETREL_NFC=', text, re.MULTILINE):
        return False
    with path.open('a') as stream:
        stream.write(('' if not text or text.endswith('\n') else '\n') + 'PETREL_NFC=0\n')
    return True


if __name__ == '__main__':
    ensure_emulator_default(sys.argv[1])
    ensure_aux_uart_default(sys.argv[1])
    ensure_nfc_default(sys.argv[1])
