"""Isolated PN532 diagnostic selection; no hardware or local native build."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from libnfc_api import library_path
from nfc_target_experiment import (
    diagnostics_enabled, diagnostics_file, diagnostics_library_path,
)
from tools import nfc_target_ab, nfc_target_diag


class PN532DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        e = patch.dict(os.environ, {
            'XDG_CONFIG_HOME': self.tmp.name,
            'XDG_DATA_HOME': self.tmp.name,
        })
        e.start()
        self.addCleanup(e.stop)
        root = Path(self.tmp.name) / 'Petrel'
        self.mode05 = root / 'libnfc-pn532-mode05'
        self.diag = root / 'libnfc-pn532-diagnostics'

    def install_mode05(self):
        lib = self.mode05 / 'lib' / 'libnfc.so.6'
        lib.parent.mkdir(parents=True, exist_ok=True)
        lib.write_bytes(b'mock')
        (self.mode05 / '.petrel-pn532-picc').write_text('mode=0x05\n')
        return str(lib)

    def install_diag(self):
        lib = self.diag / 'lib' / 'libnfc.so.6'
        lib.parent.mkdir(parents=True, exist_ok=True)
        lib.write_bytes(b'mock')
        (self.diag / '.petrel-nfc-diagnostics').write_text(
            'libnfc-1.8.0 PN532 target diagnostics mode=0x05 v1\n')
        return str(lib)

    def test_diagnostic_is_off_by_default_and_opt_in_to_A_or_B_only(self):
        regular = self.install_mode05()
        trace = self.install_diag()
        self.assertFalse(diagnostics_enabled())
        with self.assertRaisesRegex(ValueError, 'Mode 0x05'):
            nfc_target_diag.enable()
        self.assertFalse(diagnostics_file().exists())
        nfc_target_ab.select('A')
        self.assertEqual(library_path(), regular)
        self.assertEqual(nfc_target_diag.enable(), ('A', trace))
        self.assertTrue(diagnostics_enabled())
        self.assertEqual(library_path(), trace)
        self.assertEqual(diagnostics_file().stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, 'Disable'):
            nfc_target_ab.select('C')
        nfc_target_ab.select('B')
        self.assertEqual(library_path(), trace)
        nfc_target_diag.disable()
        self.assertFalse(diagnostics_enabled())
        self.assertEqual(library_path(), regular)

    def test_incomplete_or_mismatched_install_never_falls_back(self):
        self.install_mode05()
        nfc_target_ab.select('A')
        with self.assertRaisesRegex(OSError, 'not installed'):
            nfc_target_diag.enable()
        self.assertFalse(diagnostics_file().exists())
        self.install_diag()
        (self.diag / '.petrel-nfc-diagnostics').write_text('wrong')
        with self.assertRaisesRegex(OSError, 'marker'):
            nfc_target_diag.enable()
        self.assertFalse(diagnostics_file().exists())
        self.install_diag()
        nfc_target_diag.enable()
        (self.diag / 'lib' / 'libnfc.so.6').unlink()
        with self.assertRaisesRegex(OSError, 'not installed'):
            library_path()

    def test_invalid_control_marker_is_rejected(self):
        flag = diagnostics_file()
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text('garbage')
        with self.assertRaisesRegex(ValueError, 'marker'):
            diagnostics_enabled()
