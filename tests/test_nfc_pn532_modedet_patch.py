"""Pinned libnfc CIU_Mode ModeDetOff patch contracts; CI-only, no local hardware."""
import unittest

from tools.nfc_pn532_modedet_patch import (
    TARGET, TARGET_END, IDLE, IDLE_END, POINT, IDLE_POINT, patch_text,
)


class PN532ModeDetOffPatchTests(unittest.TestCase):
    def source(self):
        return (
            'int\n' + IDLE + '\n{\n'
            + '  int res = 0;\n'
            + IDLE_POINT + '\n}\n'
            + IDLE_END + '\n'
            + 'int\n' + TARGET + '\n{\n'
            + '    ptm = PTM_ISO14443_4_PICC_ONLY;\n'
            + POINT + '\n}\n'
            + TARGET_END
        )

    def test_only_mode_detector_bit_is_written_and_restored(self):
        patched = patch_text(self.source())
        self.assertIn('ptm = PTM_ISO14443_4_PICC_ONLY;', patched)
        self.assertIn('PN53X_REG_CIU_Mode, 0x04, 0x04', patched)
        self.assertIn('PN53X_REG_CIU_Mode, 0x04, 0x00', patched)
        self.assertIn('PETREL_NFC_MODEDET set addr=6301', patched)
        self.assertIn('PETREL_NFC_MODEDET restore addr=6301', patched)
        self.assertIn('PN53X_REG_CIU_TxMode, &tx', patched)
        self.assertIn('PN53X_REG_CIU_RxMode, &rx', patched)
        self.assertNotIn('pn53x_WriteRegister(pnd, PN53X_REG_CIU_TxMode', patched)

    def test_wrong_mode_duplicate_and_missing_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, '0x04 base'):
            patch_text(self.source().replace(
                'ptm = PTM_ISO14443_4_PICC_ONLY;',
                'ptm |= PTM_ISO14443_4_PICC_ONLY;'))
        once = patch_text(self.source())
        with self.assertRaisesRegex(ValueError, 'already patched'):
            patch_text(once)
        for anchor in (POINT, IDLE_POINT):
            with self.subTest(anchor=anchor[:25]):
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    patch_text(self.source().replace(anchor, 'unexpected source revision'))
