"""System libnfc ModeDetOff experiment: no custom build or local PN532 tests."""
import ctypes as C
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import libnfc_api
from libnfc_api import NFCTargetSession, Target
from nfc_target_experiment import (
    system_modedet_enabled, system_modedet_file, selected_profile,
)
from tools import (
    nfc_target_ab, nfc_target_diag, nfc_target_modedet,
    nfc_target_system_modedet,
)


class SystemRegisterExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {
            'XDG_CONFIG_HOME': self.tmp.name,
            'XDG_DATA_HOME': self.tmp.name,
        })
        env.start()
        self.addCleanup(env.stop)
        root = Path(self.tmp.name) / 'Petrel' / 'libnfc-pn532-mode05'
        (root / 'lib').mkdir(parents=True)
        (root / 'lib' / 'libnfc.so.6').write_bytes(b'fake ordinary A')
        (root / '.petrel-pn532-picc').write_text('mode=0x05\n')

    @staticmethod
    def mock_system():
        lib = Mock()
        lib.nfc_version.return_value = b'1.8.0'
        return lib

    def test_experiment_uses_system_library_not_experimental_build(self):
        nfc_target_ab.select('A')
        ordinary = libnfc_api.library_path()
        self.assertIn('libnfc-pn532-mode05', ordinary)
        with patch('tools.nfc_target_system_modedet.C.util.find_library',
                   return_value='libnfc.so.6'), \
             patch('tools.nfc_target_system_modedet.C.CDLL',
                   return_value=self.mock_system()), \
             patch('libnfc_api.C.util.find_library',
                   return_value='libnfc.so.6'):
            self.assertEqual(nfc_target_system_modedet.enable(),
                             ('libnfc.so.6', '1.8.0'))
            self.assertTrue(system_modedet_enabled())
            self.assertEqual(libnfc_api.library_path(), 'libnfc.so.6')
            self.assertEqual(system_modedet_file().stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, 'Disable'):
                nfc_target_ab.select('C')
            with self.assertRaisesRegex(ValueError, 'Disable'):
                nfc_target_ab.reset()
            with self.assertRaisesRegex(ValueError, 'Disable'):
                nfc_target_diag.enable()
            with self.assertRaisesRegex(ValueError, 'Disable'):
                nfc_target_modedet.enable()
            nfc_target_system_modedet.disable()
            self.assertFalse(system_modedet_enabled())
        self.assertEqual(libnfc_api.library_path(), ordinary)

    def test_requires_a_and_does_not_enable_if_symbol_missing(self):
        with self.assertRaisesRegex(ValueError, 'profile A'):
            nfc_target_system_modedet.enable()
        nfc_target_ab.select('A')
        with patch('tools.nfc_target_system_modedet.C.util.find_library',
                   return_value=None):
            with self.assertRaisesRegex(OSError, 'not installed'):
                nfc_target_system_modedet.enable()

        class WithoutPrivateSymbol:
            def __init__(self):
                self.nfc_version = Mock(return_value=b'1.8.0')

        with patch('tools.nfc_target_system_modedet.C.util.find_library',
                   return_value='libnfc.so.6'), \
             patch('tools.nfc_target_system_modedet.C.CDLL',
                   return_value=WithoutPrivateSymbol()):
            with self.assertRaisesRegex(OSError, 'register ABI'):
                nfc_target_system_modedet.enable()
        self.assertFalse(system_modedet_file().exists())

    def test_missing_symbol_fails_binding_not_silent_fallback(self):
        nfc_target_ab.select('A')
        system_modedet_file().write_text('enabled-v1\n')
        class NoSymbol:
            def __getattr__(self, name):
                if name == 'pn53x_write_register':
                    raise AttributeError(name)
                return Mock()
        libnfc_api.bind_library.cache_clear()
        try:
            with patch('libnfc_api.C.util.find_library', return_value='libnfc.so.6'), \
                 patch('libnfc_api.C.CDLL', return_value=NoSymbol()):
                with self.assertRaisesRegex(OSError, 'lacks pn53x_write_register'):
                    libnfc_api.bind_library()
        finally:
            libnfc_api.bind_library.cache_clear()

    def test_queued_before_each_target_init_masked_and_cleared_on_close(self):
        nfc_target_ab.select('A')
        lib = Mock()
        device = 123
        target = NFCTargetSession.__new__(NFCTargetSession)
        target.device = device
        target.lib = lib
        target.context = C.c_void_p()
        order = []
        lib.pn53x_write_register.side_effect = lambda *args: (
            order.append(('register', args)), 0)[1]
        cancelled = [False]
        def activate(*args):
            order.append(('target_init', args[-1]))
            cancelled[0] = True
            return -6
        lib.nfc_target_init.side_effect = activate
        with patch('libnfc_api.system_modedet_enabled', return_value=True), \
             patch('libnfc_api.library_path', return_value='libnfc.so.6'):
            self.assertFalse(target.serve_uri(
                'https://github.com/sezgynus/Petrel',
                lambda: cancelled[0], lambda *_: None))
            self.assertEqual(order, [
                ('register', (device, 0x6301, 0x04, 0x04)),
                ('target_init', 500),
            ])
            target.close()
        self.assertEqual(lib.pn53x_write_register.call_args.args,
                         (device, 0x6301, 0x04, 0x00))
        lib.nfc_close.assert_called_once_with(device)

    def test_write_failure_exposes_error_and_does_not_start_target(self):
        target = NFCTargetSession.__new__(NFCTargetSession)
        target.device = 123
        target.lib = Mock()
        target.lib.pn53x_write_register.return_value = -1
        with patch('libnfc_api.system_modedet_enabled', return_value=True), \
             patch('libnfc_api.library_path', return_value='libnfc.so.6'):
            with self.assertRaisesRegex(OSError, 'register write failed'):
                target.serve_uri('https://example.org', lambda: False, lambda *_: None)
        target.lib.nfc_target_init.assert_not_called()

    def test_invalid_activation_marker_is_rejected(self):
        flag = system_modedet_file()
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text('bad')
        with self.assertRaisesRegex(ValueError, 'marker'):
            system_modedet_enabled()
