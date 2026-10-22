#!/usr/bin/env python3
"""Strictly scoped source patch for libnfc 1.8.0 PN532 Type 4 tag emulation.

Upstream pn53x_target_init ORs PTM_PASSIVE_ONLY into PN532 PICC-only mode,
yielding TgInitAsTarget Mode 0x05. Petrel's experimental NDEF share wants
strict ISO14443-4A PICC mode 0x04, as in the working PN532 reference.
This change applies ONLY to the PN532 ISO14443A / 14443-4 branch.
"""
import argparse
from pathlib import Path


OLD = """          ptm |= PTM_ISO14443_4_PICC_ONLY; // We add ISO14443-4 restriction"""
NEW = """          ptm = PTM_ISO14443_4_PICC_ONLY; // Petrel: strict ISO14443-4 PICC; exclude FeliCa ghost"""
BRANCH = """if (CHIP_DATA(pnd)->type == PN532) { // We have a PN532"""


def patch_text(source, mode='04'):
    """Validate the pinned branch for both modes; only 04 modifies it."""
    if mode not in ('04', '05'):
        raise ValueError('Mode must be 04 or 05')
    if source.count(OLD) != 1:
        raise ValueError('Expected exactly one upstream PICC-only mode expression')
    begin = source.index('pn53x_target_init(struct nfc_device *pnd')
    branch = source.find(BRANCH, begin)
    position = source.find(OLD, begin)
    if branch < 0 or not begin < branch < position or position - branch > 650:
        raise ValueError('PN532 target-mode context does not match pinned libnfc')
    if mode == '05':
        return source  # Exact upstream 0x01 | 0x04; no source modification.
    return source[:position] + NEW + source[position + len(OLD):]


def patch_file(path, mode='04'):
    path = Path(path)
    previous = path.read_text()
    updated = patch_text(previous, mode=mode)
    if updated != previous:
        path.write_text(updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('04', '05'), default='04',
                        help='04: PICC only patch; 05: verified upstream code')
    parser.add_argument('source', type=Path, help='libnfc/chips/pn53x.c (libnfc-1.8.0)')
    args = parser.parse_args()
    patch_file(args.source, mode=args.mode)


if __name__ == '__main__':
    main()
