"""Direct API contracts and ABI checked against the distro's real libnfc headers."""
import ctypes as C
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from libnfc_api import NFCSession, Target, TargetInfo, Modulation, ISOA, decode_target, INT
from nfc_settings import NFCSettings


class DirectLibNFCTests(unittest.TestCase):
    def fake_library(self):
        lib = Mock()
        lib.nfc_init.side_effect = lambda out: setattr(out._obj, 'value', 1)
        lib.nfc_open.return_value = 100
        lib.nfc_initiator_init.return_value = 0
        lib.nfc_device_set_property_bool.return_value = 0
        lib.nfc_device_set_property_int.return_value = 0
        lib.nfc_initiator_deselect_target.return_value = 0
        kinds = (INT * 11)(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0)
        rates = {kind: (INT * 4)(*((3, 2, 1, 0) if kind == 1 else
                   (2, 3, 0, 0) if kind == 7 else (1, 2, 3, 0) if kind == 8 else (1, 0, 0, 0)))
                 for kind in range(1, 11)}
        def supported(device, mode, out):
            C.cast(out, C.POINTER(C.POINTER(INT)))[0] = kinds
            return 0
        def bauds(device, kind, out):
            C.cast(out, C.POINTER(C.POINTER(INT)))[0] = rates[kind]
            return 0
        lib.nfc_device_get_supported_modulation.side_effect = supported
        lib.nfc_device_get_supported_baud_rate.side_effect = bauds
        return lib

    def test_library_abi_is_resolved_once_and_reused_across_sessions(self):
        from libnfc_api import bind_library
        bind_library.cache_clear()
        try:
            with patch('libnfc_api.C.util.find_library', return_value='libnfc.so'), \
                    patch('libnfc_api.C.CDLL') as load_lib:
                first = bind_library()
                second = bind_library()
                self.assertIs(first, second)
                load_lib.assert_called_once_with('libnfc.so')
                self.assertEqual(first.nfc_open.restype, C.c_void_p)
        finally:
            bind_library.cache_clear()

    def test_connection_probe_uses_exact_draft_for_each_libnfc_driver(self):
        from libnfc_api import check_connection
        from nfc_settings import NFCSettings, PROFILES
        examples = {
            'UART': '/dev/ttyDWIN0', 'I2C': '/dev/i2c-1',
            'SPI': '/dev/spidev0.0', 'USB': 'pn53x_usb:001:003',
            'PC/SC': 'acr122_pcsc:Reader', 'NCI': 'pn71xx:Reader',
        }
        for model, profile in PROFILES.items():
            for interface in profile['interfaces']:
                with self.subTest(model=model, interface=interface):
                    port = examples[interface]
                    if interface == 'USB':
                        port = profile['drivers'][interface] + ':001:003'
                    if interface == 'PC/SC':
                        port = profile['drivers'][interface] + ':Reader'
                    setting = NFCSettings(model, interface, port,
                                          115200 if interface == 'UART' else 0)
                    lib = self.fake_library()
                    with patch('libnfc_api.bind_library', return_value=lib), \
                            patch.dict(os.environ, {'PETREL_NFC_DEVICE': 'wrong'}):
                        self.assertTrue(check_connection(setting))
                    lib.nfc_open.assert_called_once()
                    self.assertEqual(lib.nfc_open.call_args.args[0].value, 1)
                    self.assertEqual(lib.nfc_open.call_args.args[1],
                                     setting.connection_string().encode('utf-8'))
                    lib.nfc_initiator_init.assert_called_once_with(100)
                    lib.nfc_close.assert_called_once_with(100)
                    lib.nfc_exit.assert_called_once()
                    self.assertEqual(lib.nfc_exit.call_args.args[0].value, 1)

    def test_connection_probe_reports_open_and_init_failure_without_leaks(self):
        from libnfc_api import check_connection
        from nfc_settings import NFCSettings
        config = NFCSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200)
        for failure in ('open', 'init'):
            with self.subTest(failure=failure):
                lib = self.fake_library()
                if failure == 'open':
                    lib.nfc_open.return_value = 0
                else:
                    lib.nfc_initiator_init.return_value = -3
                with patch('libnfc_api.bind_library', return_value=lib), \
                        self.assertRaises(OSError):
                    check_connection(config)
                self.assertEqual(lib.nfc_close.call_count, failure != 'open')
                lib.nfc_exit.assert_called_once()
                self.assertEqual(lib.nfc_exit.call_args.args[0].value, 1)

    def test_session_requires_explicit_validated_settings_and_never_falls_back(self):
        lib = self.fake_library()
        with patch('libnfc_api.bind_library', return_value=lib), \
                patch.dict(os.environ, {'PETREL_NFC_DEVICE': 'wrong'}):
            with self.assertRaises(ValueError):
                NFCSession(NFCSettings())
            lib.nfc_open.assert_not_called()
            valid = NFCSettings('PN532', 'UART', '/dev/ttyAMA0', 115200)
            session = NFCSession(valid)
        self.assertEqual(lib.nfc_open.call_args.args[1],
                         b'pn532_uart:/dev/ttyAMA0:115200')
        session.close()

    def test_persistent_explicit_handle_and_all_advertised_card_types(self):
        lib = self.fake_library()
        with patch('libnfc_api.bind_library', return_value=lib), \
             patch.dict(os.environ, {'PETREL_NFC_DEVICE': 'pn532_uart:/dev/ttyDWIN0:115200'}):
            session = NFCSession(NFCSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200))
        self.assertEqual({kind for kind, _ in session.modulations}, set(range(1, 11)))
        self.assertEqual([rate for kind, rate in session.modulations if kind == 1], [1])
        self.assertEqual([rate for kind, rate in session.modulations if kind == 7], [2, 3])
        lib.nfc_open.assert_called_once()
        self.assertEqual(lib.nfc_open.call_args.args[1], b'pn532_uart:/dev/ttyDWIN0:115200')
        lib.nfc_initiator_select_passive_target.return_value = 0
        lib.nfc_initiator_select_dep_target.return_value = 0
        for modulation in session.modulations:
            self.assertIsNone(session.scan(modulation))
        self.assertEqual(lib.nfc_initiator_select_passive_target.call_count, 10)
        self.assertEqual(lib.nfc_initiator_select_dep_target.call_count, 3)
        lib.nfc_open.assert_called_once()
        session.abort()
        lib.nfc_abort_command.assert_called_once_with(100)
        session.close()
        session.close()
        lib.nfc_close.assert_called_once_with(100)
        lib.nfc_exit.assert_called_once()

    def test_unsupported_is_reported_and_transport_failure_is_not_a_missing_card(self):
        lib = self.fake_library()
        with patch('libnfc_api.bind_library', return_value=lib):
            session = NFCSession(NFCSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200))
        try:
            lib.nfc_initiator_select_passive_target.return_value = -3
            self.assertEqual(session.scan((3, 1)), 'unsupported')
            lib.nfc_initiator_select_passive_target.return_value = -1
            with self.assertRaises(OSError):
                session.scan((3, 1))
        finally:
            session.close()

    def test_repeated_card_selection_resets_rf_and_does_not_discard_read(self):
        lib = self.fake_library()
        lib.nfc_strerror.return_value = b'Input/output error'
        # Deselect is deliberately unusable: RF reset, not InDeselect, releases
        # the previous tag before the next activation (also for raw protocols).
        lib.nfc_initiator_deselect_target.return_value = -1
        def select(device, modulation, data, length, out):
            target = out._obj
            target.modulation = modulation
            target.info.a.uid_len = 4
            target.info.a.uid[:] = [0x6b, 0xb3, 0x9d, 0x14] + [0] * 6
            return 1
        lib.nfc_initiator_select_passive_target.side_effect = select
        with patch('libnfc_api.bind_library', return_value=lib):
            session = NFCSession(NFCSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200))
        for _ in range(3):
            self.assertEqual(session.scan((1, 1))['uid'], '6B:B3:9D:14')
        self.assertEqual(lib.nfc_initiator_init.call_count, 4)
        lib.nfc_initiator_deselect_target.assert_not_called()
        self.assertEqual(lib.nfc_device_set_property_bool.call_args.args, (100, 7, False))
        session.close()

    def test_dep_allows_firmware_retry_to_complete_and_errors_identify_protocol(self):
        lib = self.fake_library()
        lib.nfc_strerror.return_value = b'Input/output error'
        lib.nfc_initiator_select_dep_target.return_value = 0
        with patch('libnfc_api.bind_library', return_value=lib):
            session = NFCSession(NFCSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200))
        self.assertIsNone(session.scan((8, 1)))
        self.assertEqual(lib.nfc_initiator_select_dep_target.call_args.args[-1], 1000)
        lib.nfc_initiator_select_passive_target.return_value = -1
        with self.assertRaisesRegex(OSError, 'ISO14443A baud=1 select:.*-1.*Input/output'):
            session.scan((1, 1))
        session.close()

    def test_private_pn532_library_selection_is_opt_in_and_reversible(self):
        from libnfc_api import library_path
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'XDG_DATA_HOME': tmp}), \
                    patch('libnfc_api.C.util.find_library', return_value='libnfc.so.6'):
                self.assertEqual(library_path(), 'libnfc.so.6')
                root = Path(tmp) / 'Petrel' / 'libnfc-pn532-picc'
                lib = root / 'lib' / 'libnfc.so.6'
                lib.parent.mkdir(parents=True)
                lib.write_bytes(b'fake')
                self.assertEqual(library_path(), 'libnfc.so.6')
                (root / '.petrel-pn532-picc').write_text('ready')
                self.assertEqual(library_path(), str(lib))
                (root / '.petrel-pn532-picc').unlink()
                self.assertEqual(library_path(), 'libnfc.so.6')

    def test_pn532_target_emulates_type_4a_without_advertising_dep(self):
        from libnfc_api import NFCTargetSession
        target = NFCTargetSession.__new__(NFCTargetSession)
        target.device = 123
        target.lib = self.fake_library()
        parameters = []
        def activate(device, target_ptr, *_):
            param = C.cast(target_ptr, C.POINTER(Target)).contents
            a = param.info.a
            parameters.append((param.modulation.kind, bytes(a.atqa),
                               a.sak, bytes(a.uid[:a.uid_len])))
            return 0
        target.lib.nfc_target_init.side_effect = activate
        cancelled = [False]
        def receive(*args):
            cancelled[0] = True
            return -6
        target.lib.nfc_target_receive_bytes.side_effect = receive
        self.assertFalse(target.serve_uri('https://example.org',
                                         lambda: cancelled[0],
                                         lambda *args: None))
        self.assertEqual(parameters, [(1, b'\\x00\\x08', 0x20,
                                       b'\\x08\\x00\\xb0\\x0b')])

    def test_target_activation_with_no_initial_apdu_waits_for_phone(self):
        from libnfc_api import NFCTargetSession
        from unittest.mock import Mock
        target = NFCTargetSession.__new__(NFCTargetSession)
        target.device = 123
        target.lib = Mock()
        target.lib.nfc_target_init.return_value = 0
        cancelled = [False]
        def receive(*args):
            cancelled[0] = True
            return -6
        target.lib.nfc_target_receive_bytes.side_effect = receive
        self.assertFalse(target.serve_uri('https://example.org',
                                         lambda: cancelled[0],
                                         lambda *args: None))
        target.lib.nfc_target_receive_bytes.assert_called_once()
        target.lib.nfc_target_send_bytes.assert_not_called()

    def test_real_header_layout_and_c_populated_target_match_ctypes(self):
        if not shutil.which('cc') or not Path('/usr/include/nfc/nfc.h').exists():
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                self.fail('CI requires libnfc-dev and cc for ABI validation')
            self.skipTest('libnfc headers unavailable')
        source = r'''
#include <nfc/nfc.h>
#include <stddef.h>
#include <string.h>
size_t target_size(void) { return sizeof(nfc_target); }
size_t info_size(void) { return sizeof(nfc_target_info); }
size_t modulation_offset(void) { return offsetof(nfc_target, nm); }
size_t uid_offset(void) { return offsetof(nfc_iso14443a_info, abtUid); }
int fill_target(nfc_target *t, nfc_modulation m) {
  memset(t, 0, sizeof(*t)); t->nm = m;
  t->nti.nai.szUidLen = 4;
  memcpy(t->nti.nai.abtUid, "\x6b\xb3\x9d\x14", 4);
  t->nti.nai.btSak = 8;
  return m.nmt + m.nbr;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'abi.c').write_text(source)
            subprocess.run(['cc', '-Wall', '-Werror', '-shared', '-fPIC',
                str(root / 'abi.c'), '-o', str(root / 'abi.so')], check=True, capture_output=True)
            lib = C.CDLL(str(root / 'abi.so'))
            for name, expected in [('target_size', C.sizeof(Target)), ('info_size', C.sizeof(TargetInfo)),
                ('modulation_offset', Target.modulation.offset), ('uid_offset', ISOA.uid.offset)]:
                method = getattr(lib, name)
                method.restype = C.c_size_t
                self.assertEqual(method(), expected, name)
            lib.fill_target.argtypes = [C.POINTER(Target), Modulation]
            lib.fill_target.restype = INT
            target = Target()
            self.assertEqual(lib.fill_target(C.byref(target), Modulation(1, 1)), 2)
            self.assertEqual(decode_target(target)['uid'], '6B:B3:9D:14')
