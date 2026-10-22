"""Isolated register experiment selection; fake libraries, no PN532 hardware."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from libnfc_api import library_path
from nfc_target_experiment import modedet_enabled, modedet_file
from tools import nfc_target_ab, nfc_target_diag, nfc_target_modedet


class PN532ModeDetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        e = patch.dict(os.environ, {
            'XDG_DATA_HOME': self.tmp.name, 'XDG_CONFIG_HOME': self.tmp.name
        })
        e.start()
        self.addCleanup(e.stop)
        self.base = Path(self.tmp.name) / 'Petrel'
        self.install('libnfc-pn532-picc', '.petrel-pn532-picc', 'mode=0x04\n')
        self.diag = self.install('libnfc-pn532-diagnostics',
            '.petrel-nfc-diagnostics',
            'libnfc-1.8.0 PN532 target diagnostics mode=0x05 v1\n')

    def install(self, folder, marker, text):
        root = self.base / folder
        lib = root / 'lib' / 'libnfc.so.6'
        lib.parent.mkdir(parents=True, exist_ok=True)
        lib.write_bytes(b'fake lib')
        (root / marker).write_text(text)
        return str(lib)

    def test_opt_in_isolated_c_only_and_rollback(self):
        base = str(self.base / 'libnfc-pn532-picc/lib/libnfc.so.6')
        native = self.install('libnfc-pn532-modedet', '.petrel-nfc-modedet',
            'libnfc-1.8.0 PN532 ModeDetOff mode=0x04 bit=0x04 v1\n')
        with self.assertRaisesRegex(ValueError, 'profile C'):
            nfc_target_modedet.enable()
        nfc_target_ab.select('C')
        self.assertEqual(library_path(), base)
        self.assertEqual(nfc_target_modedet.enable(), native)
        self.assertEqual(library_path(), native)
        self.assertTrue(modedet_enabled())
        self.assertEqual(modedet_file().stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, 'Disable'):
            nfc_target_ab.select('A')
        with self.assertRaisesRegex(ValueError, 'Disable'):
            nfc_target_ab.reset()
        with self.assertRaisesRegex(ValueError, 'Disable'):
            nfc_target_diag.enable()
        nfc_target_modedet.disable()
        self.assertFalse(modedet_enabled())
        self.assertEqual(library_path(), base)
        nfc_target_ab.reset()

    def test_fail_closed_when_unbuilt_wrong_marker_or_missing_library(self):
        nfc_target_ab.select('C')
        with self.assertRaisesRegex(OSError, 'not installed'):
            nfc_target_modedet.enable()
        self.assertFalse(modedet_file().exists())
        native = self.install('libnfc-pn532-modedet', '.petrel-nfc-modedet',
            'unexpected marker')
        with self.assertRaisesRegex(OSError, 'marker'):
            nfc_target_modedet.enable()
        self.assertFalse(modedet_file().exists())
        (self.base / 'libnfc-pn532-modedet/.petrel-nfc-modedet').write_text(
            'libnfc-1.8.0 PN532 ModeDetOff mode=0x04 bit=0x04 v1\n')
        nfc_target_modedet.enable()
        Path(native).unlink()
        with self.assertRaisesRegex(OSError, 'not installed'):
            library_path()

    def test_corrupt_marker_rejected(self):
        flag = modedet_file()
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text('invalid')
        with self.assertRaisesRegex(ValueError, 'marker'):
            modedet_enabled()
