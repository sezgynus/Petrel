"""Regression contracts for the persistent, single-owner NFC backend."""
import unittest
from unittest.mock import Mock, patch

from nfc_backend import NFCBackend
from nfc_settings import NFCSettings


SERIAL = NFCSettings('PN532', 'UART', '/dev/ttyAMA0', 115200)
USB = NFCSettings('PN53x USB', 'USB', 'pn53x_usb:001:003', 0)


class NFCBackendTests(unittest.TestCase):
    def backend(self, **kwargs):
        with patch('nfc_backend.Thread'):
            return NFCBackend(**kwargs)

    def test_disabled_and_unconfigured_never_claim_hardware(self):
        disabled = self.backend(feature_enabled=lambda: False,
                                config_loader=Mock(return_value=SERIAL))
        self.assertIsNone(disabled._read_configuration())
        self.assertEqual(disabled.snapshot()[1], 'Disabled')
        disabled._config_loader.assert_not_called()
        refused = disabled.test_connection(SERIAL)
        with self.assertRaisesRegex(OSError, 'disabled'):
            refused.result()
        disabled.close()

        missing = self.backend(feature_enabled=lambda: True,
                               config_loader=lambda: NFCSettings())
        self.assertIsNone(missing._read_configuration())
        self.assertEqual(missing.snapshot()[1], 'Not configured')
        missing.close()

    def test_hot_reload_closes_old_session_before_opening_new_config(self):
        configured = [SERIAL]
        actions = []
        backend = None

        def make_session(settings):
            actions.append(('open', settings))
            session = Mock()
            session.identity.return_value = {'status': 'Connected'}
            session.modulations = [(1, 1)]
            session.close.side_effect = lambda: actions.append(('close', settings))
            if settings == SERIAL:
                def change(*_):
                    configured[0] = USB
                    backend.reload_configuration()
                    return None
                session.scan.side_effect = change
            else:
                def finish(*_):
                    backend._stop.set()
                    return None
                session.scan.side_effect = finish
            return session

        backend = self.backend(feature_enabled=lambda: True,
                               config_loader=lambda: configured[0],
                               session_factory=make_session)
        backend._run()
        self.assertEqual(actions, [('open', SERIAL), ('close', SERIAL),
                                   ('open', USB), ('close', USB)])
        self.assertEqual(backend._settings, USB)
        backend.close()

    def test_probe_on_unconfigured_backend_runs_without_opening_default(self):
        backend = self.backend(feature_enabled=lambda: True,
                               config_loader=lambda: NFCSettings(),
                               session_factory=Mock(),
                               probe_factory=Mock(return_value=True))
        future = backend.test_connection(SERIAL)
        self.assertTrue(backend._run_probe())
        self.assertTrue(future.result())
        backend._probe_factory.assert_called_once_with(SERIAL)
        backend._session_factory.assert_not_called()
        backend.close()

    def test_disabled_backend_refuses_hardware_discovery(self):
        backend = self.backend(feature_enabled=lambda: False)
        future = backend.discover_devices('PN53x USB', 'USB')
        with self.assertRaisesRegex(OSError, 'disabled'):
            future.result()
        self.assertIsNone(backend._discover)
        backend.close()

    def test_usb_discovery_runs_serialized_on_owner_without_unrelated_devices(self):
        reader = self.backend(feature_enabled=lambda: True,
                              config_loader=lambda: SERIAL)
        with patch('libnfc_api.list_devices', return_value=(
                'pn53x_usb:001:003', 'acr122_usb:001:005',
                'pn532_uart:/dev/ttyUSB0:115200')):
            future = reader.discover_devices('PN53x USB', 'USB')
            self.assertTrue(reader._run_discovery() is None)
            self.assertEqual(future.result(), ('pn53x_usb:001:003',))
        reader.close()

    def test_backend_events_and_target_share_stay_single_owner(self):
        changes = []
        session = Mock()
        session.identity.return_value = {'status': 'Connected'}
        session.capabilities.return_value = {
            'target_mode': True, 'ndef_uri_emulation': True}
        session.modulations = [(1, 1)]
        reader = None
        attempts = []
        def scan(modulation):
            attempts.append('scan')
            if attempts.count('scan') == 1:
                reader.share_ndef_uri('https://example.org/guide')
            else:
                reader._stop.set()
            return None
        session.scan.side_effect = scan
        target = Mock()
        target.serve_uri.side_effect = lambda url, cancel, emit: (
            emit('share.ndef_transferred', {'url': url}) or True)
        def open_session(settings):
            attempts.append('open')
            return session
        session.close.side_effect = lambda: attempts.append('close')
        target.close.side_effect = lambda: attempts.append('target_close')
        reader = self.backend(feature_enabled=lambda: True,
                              config_loader=lambda: SERIAL,
                              session_factory=open_session,
                              target_factory=lambda settings: target)
        reader.set_event_sink(lambda event, data: changes.append(event))
        reader._run()
        self.assertIn('share.ndef_transferred', changes)
        self.assertIn('capabilities.changed', changes)
        self.assertLess(attempts.index('close'), attempts.index('target_close'))
        self.assertEqual(reader.capabilities()['ndef_uri_emulation'], True)
        reader.close()

    def test_reconfigure_resets_last_card_and_pending_arrival(self):
        backend = self.backend(feature_enabled=lambda: True,
                               config_loader=lambda: SERIAL)
        backend._observe_card((1, 1), {'uid': '12:34', 'type': 'ISO14443A'})
        backend._publish('Listening', {'uid': '12:34', 'type': 'ISO14443A'})
        self.assertTrue(backend.snapshot()[2])
        backend._read_configuration()
        self.assertEqual(backend.snapshot()[2], {})
        self.assertFalse(backend.take_card_event())
        backend.close()
