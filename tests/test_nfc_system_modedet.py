"""Production PN532 Type 4 register behavior; no profile or opt-in state."""
import ctypes as C
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import libnfc_api
from libnfc_api import (
    NFCTargetSession, Target, PN532_TARGET_ATQA,
    PN532_MODEDET_ADDRESS, PN532_MODEDET_MASK, bind_pn532_register,
)


class PN532NativeRegisterTests(unittest.TestCase):
    @staticmethod
    def session(pn532=True):
        instance = NFCTargetSession.__new__(NFCTargetSession)
        instance.device = 123
        instance.context = C.c_void_p()
        instance.lib = Mock()
        instance.lib.pn53x_write_register.return_value = 0
        instance._pn532_target = pn532
        return instance

    def test_driver_always_uses_stock_system_library_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp, 'XDG_DATA_HOME': tmp}), \
                patch('libnfc_api.C.util.find_library', return_value='libnfc.so.6'):
            config = Path(tmp) / 'Petrel'
            config.mkdir()
            (config / 'nfc-target-experiment.json').write_text('{"profile":"D"}')
            (config / 'nfc-target-system-modedet.enabled').write_text('enabled-v1\n')
            self.assertEqual(libnfc_api.library_path(), 'libnfc.so.6')
            self.assertEqual(PN532_TARGET_ATQA, (0x00, 0x04))
            self.assertEqual((PN532_MODEDET_ADDRESS, PN532_MODEDET_MASK), (0x6301, 0x04))

    def test_private_register_symbol_is_fail_closed_for_pn532(self):
        class Missing:
            def __getattr__(self, name):
                raise AttributeError(name)
        with self.assertRaisesRegex(OSError, 'lacks pn53x_write_register'):
            bind_pn532_register(Missing())
        lib = Mock()
        writer = bind_pn532_register(lib)
        self.assertIs(writer, lib.pn53x_write_register)
        self.assertEqual(writer.restype, C.c_int)
        self.assertEqual(writer.argtypes, [
            C.c_void_p, C.c_uint16, C.c_uint8, C.c_uint8])

    def test_masked_write_precedes_each_pn532_activation_and_close_clears(self):
        target = self.session()
        order = []
        cancelled = [False]
        target.lib.pn53x_write_register.side_effect = lambda *args: (
            order.append(('write', args)), 0)[1]
        def activate(*args):
            order.append(('activate', args[-1]))
            cancelled[0] = True
            return -6
        target.lib.nfc_target_init.side_effect = activate
        self.assertFalse(target.serve_uri('https://example.org',
                                         lambda: cancelled[0], lambda *_: None))
        self.assertEqual(order, [
            ('write', (123, 0x6301, 0x04, 0x04)),
            ('activate', 500),
        ])
        target.close()
        self.assertEqual(target.lib.pn53x_write_register.call_args.args,
                         (123, 0x6301, 0x04, 0x00))
        target.lib.nfc_close.assert_called_once_with(123)

    def test_non_pn532_target_does_not_access_pn532_register(self):
        target = self.session(pn532=False)
        cancelled = [False]
        def activate(*args):
            cancelled[0] = True
            return -6
        target.lib.nfc_target_init.side_effect = activate
        self.assertFalse(target.serve_uri('https://example.org',
                                         lambda: cancelled[0], lambda *_: None))
        target.close()
        target.lib.pn53x_write_register.assert_not_called()

    def test_register_failure_does_not_attempt_activation(self):
        target = self.session()
        target.lib.pn53x_write_register.return_value = -1
        with self.assertRaisesRegex(OSError, 'ModeDetOff register write failed'):
            target.serve_uri('https://example.org', lambda: False, lambda *_: None)
        target.lib.nfc_target_init.assert_not_called()

    def test_pn532_integration_requires_export_only_for_target_session(self):
        from nfc_settings import NFCSettings
        lib = Mock()
        lib.pn53x_write_register.return_value = 0
        lib.nfc_init.side_effect = lambda out: setattr(out._obj, 'value', 1)
        lib.nfc_open.return_value = 123
        with patch('libnfc_api.bind_library', return_value=lib), \
             patch('libnfc_api.bind_pn532_register') as bind:
            target = NFCTargetSession(NFCSettings('PN532', 'UART', '/dev/ttyAMA0', 115200))
            bind.assert_called_once_with(lib)
            target.close()
        with patch('libnfc_api.bind_library', return_value=lib), \
             patch('libnfc_api.bind_pn532_register') as bind:
            target = NFCTargetSession(NFCSettings('ACR122S', 'UART', '/dev/ttyUSB0', 115200))
            bind.assert_not_called()
            target.close()
