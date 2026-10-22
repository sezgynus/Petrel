#!/usr/bin/env python3
"""One-variable PN532 CIU_Mode.ModeDetOff hardware experiment.

Apply after the pinned upstream libnfc 1.8.0 Mode=0x04 patch. Do not
modify TgInitAsTarget Mode, MIFARE/FeliCa params or ISO14443A settings.
The experiment is opt-in and restores bit 2 when target mode becomes idle.
"""
import argparse
from pathlib import Path

TARGET = 'pn53x_target_init(struct nfc_device *pnd,'
IDLE = 'pn53x_idle(struct nfc_device *pnd)'
TARGET_END = '\nint\npn53x_target_receive_bits('
IDLE_END = '\nint\npn53x_check_communication('
POINT = '''  uint8_t abtMifareParams[6];'''
INSERT = '''  // Petrel experiment: disable AutoColl data-mode detection (CIU_Mode bit 2).
  // Keep all other bits and all target parameters unchanged.
  if (CHIP_DATA(pnd)->type == PN532) {
    uint8_t before = 0, after = 0, tx = 0, rx = 0;
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_Mode, &before)) < 0)
      return res;
    if ((res = pn53x_write_register(pnd, PN53X_REG_CIU_Mode, 0x04, 0x04)) < 0)
      return res;
    // ReadRegister flushes any pending libnfc register writeback first.
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_Mode, &after)) < 0)
      return res;
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_TxMode, &tx)) < 0)
      return res;
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_RxMode, &rx)) < 0)
      return res;
    fprintf(stderr,
            "PETREL_NFC_MODEDET set addr=6301 mask=04 before=%02X after=%02X "
            "txmode=%02X rxmode=%02X\\n", before, after, tx, rx);
    if ((after & 0x04) == 0)
      return NFC_EIO; // No silent fallback when the bit cannot be applied.
  }

'''
IDLE_POINT = '''    case TARGET:\n'''
IDLE_INSERT = '''  // Petrel experiment: restore ModeDetOff when leaving target operation.
  // Do not alter unrelated bits or the hardware's saved framing parameters.
  if ((CHIP_DATA(pnd)->type == PN532) &&
      (CHIP_DATA(pnd)->operating_mode == TARGET)) {
    uint8_t mode = 0;
    if ((res = pn53x_write_register(pnd, PN53X_REG_CIU_Mode, 0x04, 0x00)) < 0)
      return res;
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_Mode, &mode)) < 0)
      return res;
    fprintf(stderr, "PETREL_NFC_MODEDET restore addr=6301 after=%02X\\n", mode);
    if (mode & 0x04)
      return NFC_EIO;
  }
'''
def single(text, anchor, replacement):
    if text.count(anchor) != 1:
        raise ValueError('Pinned libnfc source mismatch near ' + anchor[:60])
    return text.replace(anchor, replacement, 1)


def patch_text(source):
    if 'PETREL_NFC_MODEDET' in source:
        raise ValueError('ModeDetOff experiment already patched')
    # Require pinned, previously applied strict 0x04 variant; reject upstream 0x05.
    if source.count('ptm = PTM_ISO14443_4_PICC_ONLY;') != 1:
        raise ValueError('ModeDetOff experiment requires the verified 0x04 base')
    if source.count('ptm |= PTM_ISO14443_4_PICC_ONLY;') != 0:
        raise ValueError('ModeDetOff experiment cannot use upstream 0x05')
    a = source.index(TARGET)
    b = source.index(TARGET_END, a)
    source = source[:a] + single(source[a:b], POINT, INSERT + POINT) + source[b:]
    a = source.index(IDLE)
    b = source.index(IDLE_END, a)
    source = source[:a] + single(
        source[a:b], IDLE_POINT, IDLE_INSERT + IDLE_POINT) + source[b:]
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    original = args.source.read_text()
    args.source.write_text(patch_text(original))


if __name__ == '__main__':
    main()
