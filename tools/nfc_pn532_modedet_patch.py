#!/usr/bin/env python3
"""Isolated PN532 CIU_Mode.ModeDetOff hardware experiment, upstream 0x05 or 0x04.

Source patch is limited to pn53x.c. Both variants set/restore ONLY bit 2 of
CIU_Mode 0x6301 and retain the original target mode and target parameters.
Instrumentation records phase-specific failures; it adds no RF commands.
"""
import argparse
from pathlib import Path

TARGET = 'pn53x_target_init(struct nfc_device *pnd,'
IDLE = 'pn53x_idle(struct nfc_device *pnd)'
TARGET_END = '\nint\npn53x_target_receive_bits('
IDLE_END = '\nint\npn53x_check_communication('
HELPER = 'pn53x_TgInitAsTarget(struct nfc_device *pnd,'
HELPER_END = '\nint\npn53x_check_ack_frame('
POINT = '  uint8_t abtMifareParams[6];'
IDLE_POINT = '    case TARGET:\n'
MODE04 = 'ptm = PTM_ISO14443_4_PICC_ONLY;'
MODE05 = 'ptm |= PTM_ISO14443_4_PICC_ONLY;'

INSERT = r'''  // Experiment only: mask-write CIU_Mode.ModeDetOff, do not change target Mode.
  if (CHIP_DATA(pnd)->type == PN532) {
    uint8_t before = 0, after = 0, tx = 0, rx = 0;
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_Mode, &before)) < 0) {
      fprintf(stderr, "PETREL_NFC_MODEDET error phase=set_read_before rc=%d\n", res);
      return res;
    }
    if ((res = pn53x_write_register(pnd, PN53X_REG_CIU_Mode, 0x04, 0x04)) < 0) {
      fprintf(stderr, "PETREL_NFC_MODEDET error phase=set_write rc=%d\n", res);
      return res;
    }
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_Mode, &after)) < 0) {
      fprintf(stderr, "PETREL_NFC_MODEDET error phase=set_read_after rc=%d\n", res);
      return res;
    }
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_TxMode, &tx)) < 0) {
      fprintf(stderr, "PETREL_NFC_MODEDET error phase=set_txmode rc=%d\n", res);
      return res;
    }
    if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_RxMode, &rx)) < 0) {
      fprintf(stderr, "PETREL_NFC_MODEDET error phase=set_rxmode rc=%d\n", res);
      return res;
    }
    fprintf(stderr,
            "PETREL_NFC_MODEDET set addr=6301 mask=04 before=%02X after=%02X "
            "txmode=%02X rxmode=%02X\n", before, after, tx, rx);
    if ((after & 0x04) == 0) {
      fprintf(stderr, "PETREL_NFC_MODEDET error phase=set_verify rc=%d value=%02X\n",
              NFC_EIO, after);
      return NFC_EIO;
    }
  }

'''

IDLE_INSERT = r'''      // Restore ModeDetOff before the original InRelease / powerdown sequence.
      if (CHIP_DATA(pnd)->type == PN532) {
        uint8_t mode = 0;
        if ((res = pn53x_write_register(pnd, PN53X_REG_CIU_Mode, 0x04, 0x00)) < 0) {
          fprintf(stderr, "PETREL_NFC_MODEDET error phase=restore_write rc=%d\n", res);
          return res;
        }
        if ((res = pn53x_read_register(pnd, PN53X_REG_CIU_Mode, &mode)) < 0) {
          fprintf(stderr, "PETREL_NFC_MODEDET error phase=restore_read rc=%d\n", res);
          return res;
        }
        fprintf(stderr, "PETREL_NFC_MODEDET restore addr=6301 after=%02X\n", mode);
        if (mode & 0x04) {
          fprintf(stderr, "PETREL_NFC_MODEDET error phase=restore_verify rc=%d value=%02X\n",
                  NFC_EIO, mode);
          return NFC_EIO;
        }
      }
'''
TARGET_ERROR = '''    if ((res = pn53x_TgInitAsTarget(pnd, ptm, pbtMifareParams, pbtTkt, szTkt, pbtFeliCaParams, pbtNFCID3t, pbtGBt, szGBt, pbtRx, szRxLen, &btActivatedMode, timeout)) < 0) {
      if (res == NFC_ETIMEOUT) {
        pn53x_idle(pnd);
      }
      return res;
    }'''
TARGET_ERROR_NEW = r'''    if ((res = pn53x_TgInitAsTarget(pnd, ptm, pbtMifareParams, pbtTkt, szTkt, pbtFeliCaParams, pbtNFCID3t, pbtGBt, szRxLen ? szGBt : szGBt, pbtRx, szRxLen, &btActivatedMode, timeout)) < 0) {
      if (CHIP_DATA(pnd)->type == PN532)
        fprintf(stderr, "PETREL_NFC_MODEDET target_fail phase=tg_init rc=%d mode=%02X\n",
                res, (unsigned int)ptm);
      if (res == NFC_ETIMEOUT) {
        int idle_rc = pn53x_idle(pnd);
        if (CHIP_DATA(pnd)->type == PN532 && idle_rc < 0)
          fprintf(stderr, "PETREL_NFC_MODEDET error phase=timeout_idle rc=%d\n", idle_rc);
      }
      return res;
    }
    if (CHIP_DATA(pnd)->type == PN532)
      fprintf(stderr, "PETREL_NFC_MODEDET target_activated mode=%02X command_mode=%02X\n",
              btActivatedMode, (unsigned int)ptm);'''
# Keep exactly original TgInitAsTarget args; avoid any behavioral change.
TARGET_ERROR_NEW = TARGET_ERROR_NEW.replace('szRxLen ? szGBt : szGBt', 'szGBt')

TX = '''  if ((res = pn53x_transceive(pnd, abtCmd, 36 + szOptionalBytes, abtRx, szRx, timeout)) < 0)
    return res;'''
TX_NEW = r'''  if ((res = pn53x_transceive(pnd, abtCmd, 36 + szOptionalBytes, abtRx, szRx, timeout)) < 0) {
    if (CHIP_DATA(pnd)->type == PN532)
      fprintf(stderr, "PETREL_NFC_MODEDET transceive_fail phase=tg_init rc=%d cmd_mode=%02X timeout=%d\n",
              res, abtCmd[1], timeout);
    return res;
  }'''

def single(src, old, new, location):
    if src.count(old) != 1:
        raise ValueError('Pinned libnfc source mismatch in ' + location)
    return src.replace(old, new, 1)


def patch_text(source, mode='04'):
    if mode not in ('04', '05'):
        raise ValueError('Mode must be 04 or 05')
    if 'PETREL_NFC_MODEDET' in source:
        raise ValueError('ModeDetOff experiment already patched')
    expected, forbidden = (MODE04, MODE05) if mode == '04' else (MODE05, MODE04)
    if source.count(expected) != 1 or source.count(forbidden) != 0:
        raise ValueError('ModeDetOff experiment requires matching 0x%s source' % mode)
    a = source.index(TARGET)
    b = source.index(TARGET_END, a)
    section = source[a:b]
    section = single(section, POINT, INSERT + POINT, 'target init register')
    section = single(section, TARGET_ERROR, TARGET_ERROR_NEW, 'target init outcome')
    source = source[:a] + section + source[b:]
    a = source.index(IDLE)
    b = source.index(IDLE_END, a)
    section = source[a:b]
    section = single(section, IDLE_POINT, IDLE_POINT + IDLE_INSERT, 'target idle')
    target_idle, rest_idle = section.split('    case INITIATOR:', 1)
    target_idle = single(target_idle, '''      if ((res = pn53x_InRelease(pnd, 0)) < 0) {
        return res;
      }''',
        r'''      if ((res = pn53x_InRelease(pnd, 0)) < 0) {
        fprintf(stderr, "PETREL_NFC_MODEDET error phase=idle_inrelease rc=%d\n", res);
        return res;
      }''', 'target idle InRelease')
    target_idle = single(target_idle, '''        if ((res = pnd->driver->powerdown(pnd)) < 0) {
          return res;
        }''',
        r'''        if ((res = pnd->driver->powerdown(pnd)) < 0) {
          fprintf(stderr, "PETREL_NFC_MODEDET error phase=idle_powerdown rc=%d\n", res);
          return res;
        }''', 'target idle powerdown')
    section = target_idle + '    case INITIATOR:' + rest_idle
    source = source[:a] + section + source[b:]
    a = source.index(HELPER)
    b = source.index(HELPER_END, a)
    section = single(source[a:b], TX, TX_NEW, 'TgInitAsTarget transceive')
    return source[:a] + section + source[b:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('04', '05'), default='04')
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    args.source.write_text(patch_text(args.source.read_text(), mode=args.mode))


if __name__ == '__main__':
    main()
