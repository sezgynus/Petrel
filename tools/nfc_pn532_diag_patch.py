#!/usr/bin/env python3
"""Instrument pinned libnfc 1.8.0 PN532 target activation without changing mode.

The diagnostic build is deliberately based on the unmodified upstream 0x05
branch. Only observation statements are inserted into pn53x.c; existing
control-flow and target parameters are unchanged.
"""
import argparse
from pathlib import Path

START = 'pn53x_target_init(struct nfc_device *pnd,'
END = '\nint\npn53x_target_receive_bits('
HELPER = 'pn53x_TgInitAsTarget(struct nfc_device *pnd,'
HELPER_END = '\nint\npn53x_check_ack_frame('

PREP = '''  // Request the initialization as a target
  uint8_t  abtRx[PN53x_EXTENDED_FRAME__DATA_MAX_LEN];'''
PREP_TRACE = '''  if (CHIP_DATA(pnd)->type == PN532) {
    fprintf(stderr, "PETREL_NFC_DIAG tx cmd=8C mode=%02X mifare=", abtCmd[1]);
    for (size_t i = 2; i < 8; i++) fprintf(stderr, "%02X", abtCmd[i]);
    fprintf(stderr, " felica=");
    for (size_t i = 8; i < 26; i++) fprintf(stderr, "%02X", abtCmd[i]);
    fprintf(stderr, " hist_len=%zu timeout_ms=%d\\n", szTkt, timeout);
  }
'''
CALL = '''  if ((res = pn53x_transceive(pnd, abtCmd, 36 + szOptionalBytes, abtRx, szRx, timeout)) < 0)
    return res;'''
CALL_TRACE = '''  if ((res = pn53x_transceive(pnd, abtCmd, 36 + szOptionalBytes, abtRx, szRx, timeout)) < 0) {
    if (CHIP_DATA(pnd)->type == PN532)
      fprintf(stderr, "PETREL_NFC_DIAG tx_result error=%d timeout_ms=%d\\n", res, timeout);
    return res;
  }'''
RX = '''  if (pbtModeByte) {
    *pbtModeByte = abtRx[0];
  }'''
RX_TRACE = '''  if (pbtModeByte) {
    *pbtModeByte = abtRx[0];
  }
  if (CHIP_DATA(pnd)->type == PN532)
    fprintf(stderr, "PETREL_NFC_DIAG rx activated_mode=%02X response_len=%zu\\n",
            abtRx[0], szRx);'''
DECIDE = '''    if (targetActivated) {
      pnt->nm.nbr = nm.nbr; // Update baud rate'''
DECIDE_TRACE = '''    if (CHIP_DATA(pnd)->type == PN532)
      fprintf(stderr,
              "PETREL_NFC_DIAG activation mode=%02X wanted_nmt=%d actual_nmt=%d "
              "baud=%d accepted=%d\\n",
              btActivatedMode, (int)pnt->nm.nmt, (int)nm.nmt,
              (int)nm.nbr, (int)targetActivated);
    if (targetActivated) {
      pnt->nm.nbr = nm.nbr; // Update baud rate'''

def replace_one(src, old, new, label):
    if src.count(old) != 1:
        raise ValueError('Pinned libnfc source mismatch at ' + label)
    return src.replace(old, new, 1)


def patch_text(src):
    """Return modified source, refusing unknown or previously patched versions."""
    if 'PETREL_NFC_DIAG' in src:
        raise ValueError('Diagnostic patch already applied')
    if START not in src or END not in src or HELPER not in src or HELPER_END not in src:
        raise ValueError('Expected PN532 functions not found')
    a = src.index(START)
    b = src.index(END, a)
    init = src[a:b]
    # Reject any previously applied 0x04 PICC-only patch.
    upstream = 'ptm |= PTM_ISO14443_4_PICC_ONLY; // We add ISO14443-4 restriction'
    if init.count(upstream) != 1:
        raise ValueError('Diagnostic mode must use unmodified upstream 0x05 branch')
    init = replace_one(init, DECIDE, DECIDE_TRACE, 'activation decision')
    src = src[:a] + init + src[b:]
    a = src.index(HELPER)
    b = src.index(HELPER_END, a)
    helper = src[a:b]
    helper = replace_one(helper, PREP, PREP_TRACE + PREP, 'target TX')
    helper = replace_one(helper, CALL, CALL_TRACE, 'target result')
    helper = replace_one(helper, RX, RX_TRACE, 'target RX')
    return src[:a] + helper + src[b:]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    args = p.parse_args()
    source = args.source.read_text()
    args.source.write_text(patch_text(source))


if __name__ == '__main__':
    main()
