"""Deterministic PN532 Mode/ATQA A-B matrix; mock-only CI contracts."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import libnfc_api
from nfc_target_experiment import (
    PROFILES, config_file, library_for_mode, selected_profile, target_atqa,
)
from tools import nfc_target_ab


class PN532TargetMatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            'XDG_DATA_HOME': self.tmp.name,
            'XDG_CONFIG_HOME': self.tmp.name,
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def fake_install(self, mode):
        root = Path(self.tmp.name) / 'Petrel' / (
            'libnfc-pn532-picc' if mode == 0x04 else 'libnfc-pn532-mode05')
        lib = root / 'lib' / 'libnfc.so.6'
        lib.parent.mkdir(parents=True, exist_ok=True)
        lib.write_bytes(b'fake library for profile-selection test only')
        (root / '.petrel-pn532-picc').write_text(
            'libnfc-1.8.0 PN532 Type4 test mode=0x%02X\n' % mode)
        return str(lib)

    def test_four_orthogonal_profiles(self):
        self.assertEqual(PROFILES, {
            'A': (0x05, (0x00, 0x04)),
            'B': (0x05, (0x00, 0x08)),
            'C': (0x04, (0x00, 0x04)),
            'D': (0x04, (0x00, 0x08)),
        })
        with patch('libnfc_api.C.util.find_library', return_value='libnfc.so.6'):
            self.assertIsNone(selected_profile())
            self.assertEqual(target_atqa(), (0x00, 0x08))
            self.assertEqual(libnfc_api.library_path(), 'libnfc.so.6')
        libs = {mode: self.fake_install(mode) for mode in (0x04, 0x05)}
        for name, (mode, atqa) in PROFILES.items():
            with self.subTest(profile=name):
                self.assertEqual(nfc_target_ab.select(name), (mode, atqa))
                self.assertEqual(selected_profile(), name)
                self.assertEqual(target_atqa(), atqa)
                self.assertEqual(library_for_mode(mode), libs[mode])
                self.assertEqual(libnfc_api.library_path(), libs[mode])
        self.assertEqual(config_file().stat().st_mode & 0o777, 0o600)
        nfc_target_ab.reset()
        self.assertIsNone(selected_profile())
        self.assertEqual(target_atqa(), (0x00, 0x08))

    def test_missing_or_mismatched_library_never_silently_falls_back(self):
        with self.assertRaisesRegex(OSError, 'not installed'):
            nfc_target_ab.select('B')
        self.assertFalse(config_file().exists())
        target = self.fake_install(0x05)
        self.assertTrue(Path(target).exists())
        root = Path(target).parents[1]
        (root / '.petrel-pn532-picc').write_text('mode=0x04')
        with self.assertRaisesRegex(OSError, 'does not match'):
            nfc_target_ab.select('A')
        self.assertFalse(config_file().exists())
        (root / '.petrel-pn532-picc').write_text('mode=0x05')
        nfc_target_ab.select('B')
        Path(target).unlink()
        with self.assertRaisesRegex(OSError, 'not installed'):
            libnfc_api.library_path()

    def test_corrupt_or_unsupported_selection_rejected(self):
        target = config_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        for payload in (
            'not json', '[]', '{}', '{"profile":"Q"}',
            '{"profile":"A","atqa":"custom"}', '{"profile":5}',
        ):
            with self.subTest(payload=payload):
                target.write_text(payload)
                with self.assertRaises(ValueError):
                    selected_profile()
        target.unlink()
