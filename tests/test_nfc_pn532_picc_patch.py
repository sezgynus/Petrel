"""Private libnfc PN532 target-mode source patch contracts (no local build)."""
import unittest

from tools.nfc_pn532_picc_patch import BRANCH, NEW, OLD, patch_text


class PN532PICCSourcePatchTests(unittest.TestCase):
    @staticmethod
    def upstream_snippet():
        return (
            'int\npn53x_target_init(struct nfc_device *pnd, nfc_target *pnt, '
            'uint8_t *pbtRx, const size_t szRxLen, int timeout)\n'
            '  switch (pnt->nm.nmt) {\n'
            '    case NMT_ISO14443A:\n'
            '      ptm = PTM_PASSIVE_ONLY;\n'
            '      ' + BRANCH + '\n'
            '        if ((pnt->nti.nai.btSak & SAK_ISO14443_4_COMPLIANT)'
            ' && (pnd->bAutoIso14443_4)) {\n'
            + OLD + '\n'
            '        }\n'
            '      }\n'
            '    case NMT_FELICA:\n'
            '      ptm = PTM_PASSIVE_ONLY;\n'
        )

    def test_exactly_one_iso14443_4_pn532_branch_becomes_picc_only(self):
        upstream = self.upstream_snippet()
        result = patch_text(upstream)
        self.assertIn(NEW, result)
        self.assertNotIn(OLD, result)
        self.assertIn('case NMT_FELICA:\n      ptm = PTM_PASSIVE_ONLY;', result)
        self.assertIn('case NMT_ISO14443A:\n      ptm = PTM_PASSIVE_ONLY;', result)

    def test_unrecognized_upstream_revision_is_rejected(self):
        upstream = self.upstream_snippet()
        with self.assertRaises(ValueError):
            patch_text(upstream.replace(OLD, 'ptm = 0x05;'))
        with self.assertRaises(ValueError):
            patch_text(upstream + OLD)
        with self.assertRaises(ValueError):
            patch_text(patch_text(upstream))
