"""PN532 observation-only patch contracts for the pinned upstream 1.8.0 C source."""
import unittest

from tools.nfc_pn532_diag_patch import (
    START, END, HELPER, HELPER_END, PREP, CALL, RX, DECIDE, patch_text,
)


class PN532DiagnosticPatchTests(unittest.TestCase):
    def upstream_stub(self):
        return (
            'int\n' + START + ' something\n{\n'
            '    ptm |= PTM_ISO14443_4_PICC_ONLY; // We add ISO14443-4 restriction\n'
            + DECIDE + '\n}\n' + END + '\nint\n'
            + HELPER + ' something\n{\n'
            + PREP + '\n'
            + CALL + '\n'
            + RX + '\n}\n'
            + HELPER_END
        )

    def test_observation_only_does_not_change_upstream_mode(self):
        source = self.upstream_stub()
        patched = patch_text(source)
        self.assertIn('ptm |= PTM_ISO14443_4_PICC_ONLY;', patched)
        self.assertNotIn('ptm = PTM_ISO14443_4_PICC_ONLY;', patched)
        self.assertIn('PETREL_NFC_DIAG tx cmd=8C mode=%02X mifare=', patched)
        self.assertIn('PETREL_NFC_DIAG rx activated_mode=', patched)
        self.assertIn('PETREL_NFC_DIAG activation mode=', patched)
        self.assertIn('PETREL_NFC_DIAG tx_result error=', patched)
        self.assertIn('for (size_t i = 8; i < 26; i++)', patched)
        self.assertIn('timeout_ms=%d', patched)

    def test_patch_fails_closed_if_wrong_source_or_double_applied(self):
        source = self.upstream_stub()
        with self.assertRaises(ValueError):
            patch_text(patch_text(source))
        with self.assertRaisesRegex(ValueError, 'unmodified upstream'):
            patch_text(source.replace(
                'ptm |= PTM_ISO14443_4_PICC_ONLY;',
                'ptm = PTM_ISO14443_4_PICC_ONLY;'))
        for old in (PREP, CALL, RX, DECIDE):
            with self.subTest(missing=old[:20]):
                with self.assertRaises(ValueError):
                    patch_text(source.replace(old, 'no matching original instruction'))
