"""Pinned libnfc PN532 ModeDetOff 0x04/0x05 native patch contracts."""
import unittest

from tools.nfc_pn532_modedet_patch import (
    TARGET, TARGET_END, IDLE, IDLE_END, HELPER, HELPER_END,
    POINT, IDLE_POINT, TARGET_ERROR, TX, patch_text,
)


class PN532ModeDetOffPatchTests(unittest.TestCase):
    def source(self, mode='04'):
        assign = ('    ptm = PTM_ISO14443_4_PICC_ONLY;\n'
                  if mode == '04' else
                  '    ptm |= PTM_ISO14443_4_PICC_ONLY;\n')
        return (
            'int\n' + IDLE + '\n{\n'
            + '  int res = 0;\n'
            + '  switch (CHIP_DATA(pnd)->operating_mode) {\n'
            + IDLE_POINT
            + '      if ((res = pn53x_InRelease(pnd, 0)) < 0) {\n'
            + '        return res;\n'
            + '      }\n'
            + '        if ((res = pnd->driver->powerdown(pnd)) < 0) {\n'
            + '          return res;\n'
            + '        }\n'
            + '      break;\n'
            + '    case INITIATOR:\n      break;\n'
            + '  }\n}\n'
            + IDLE_END + '\n'
            + 'int\n' + TARGET + '\n{\n'
            + assign + POINT + '\n'
            + TARGET_ERROR + '\n}\n'
            + TARGET_END + '\n'
            + 'int\n' + HELPER + '\n{\n'
            + TX + '\n}\n'
            + HELPER_END
        )

    def test_register_writes_and_stage_specific_logging_for_both_modes(self):
        for mode in ('04', '05'):
            with self.subTest(mode=mode):
                source = self.source(mode)
                patched = patch_text(source, mode=mode)
                self.assertIn('PN53X_REG_CIU_Mode, 0x04, 0x04', patched)
                self.assertIn('PN53X_REG_CIU_Mode, 0x04, 0x00', patched)
                self.assertIn('PETREL_NFC_MODEDET set addr=6301', patched)
                self.assertIn('PETREL_NFC_MODEDET restore addr=6301', patched)
                self.assertIn('phase=set_write', patched)
                self.assertIn('phase=restore_verify', patched)
                self.assertIn('phase=idle_inrelease', patched)
                self.assertIn('phase=timeout_idle', patched)
                self.assertIn('phase=tg_init', patched)
                self.assertIn('target_activated mode=', patched)
                self.assertIn('PN53X_REG_CIU_TxMode, &tx', patched)
                self.assertIn('PN53X_REG_CIU_RxMode, &rx', patched)
                self.assertGreater(patched.index('PETREL_NFC_MODEDET restore'),
                                   patched.index('case TARGET:'))
                self.assertLess(patched.index('PETREL_NFC_MODEDET restore'),
                                patched.index('case INITIATOR:'))
                # Mode expression is unchanged, not substituted by the register patch.
                expression = ('ptm = PTM_ISO14443_4_PICC_ONLY;' if mode == '04'
                              else 'ptm |= PTM_ISO14443_4_PICC_ONLY;')
                self.assertIn(expression, patched)
                self.assertEqual(patched.count(expression), 1)
                self.assertNotIn('PN53X_REG_CIU_TxMode, 0xFF', patched)

    def test_wrong_source_mode_duplicate_patch_or_missing_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'matching 0x05'):
            patch_text(self.source('04'), mode='05')
        with self.assertRaisesRegex(ValueError, 'matching 0x04'):
            patch_text(self.source('05'), mode='04')
        once = patch_text(self.source('05'), mode='05')
        with self.assertRaisesRegex(ValueError, 'already patched'):
            patch_text(once, mode='05')
        for anchor in (POINT, IDLE_POINT, TARGET_ERROR, TX):
            with self.subTest(missing=anchor[:35]):
                with self.assertRaises(ValueError):
                    patch_text(self.source('05').replace(
                        anchor, 'unexpected pinned upstream'), mode='05')
