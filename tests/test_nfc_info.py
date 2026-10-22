"""NFC Info discovery stays asynchronous, scoped and cached."""
from concurrent.futures import Future
import subprocess
import unittest
from unittest.mock import Mock, patch

from nfc_info import parse_info
from test_capabilities import display, printer, snapshot

OUTPUT = '''nfc-scan-device uses libnfc 1.8.0
1 NFC device(s) found:
- pn532_uart:/dev/ttyDWIN0:
    pn532_uart:/dev/ttyDWIN0:115200
chip: PN532 v1.6
initator mode modulations: ISO/IEC 14443A (106 kbps), ISO/IEC 14443B (106 kbps), FeliCa (212 kbps)
target mode modulations: ISO/IEC 14443A (106 kbps)
'''


class NFCInfoTests(unittest.TestCase):
    def test_identity_from_libnfc_and_no_invented_hardware_revision(self):
        info = parse_info(OUTPUT)
        self.assertEqual(info['model'], 'PN532')
        self.assertEqual(info['firmware'], '1.6')
        self.assertEqual(info['library'], '1.8.0')
        self.assertEqual(info['hardware'], 'Not reported')
        self.assertEqual((info['iso_a'], info['iso_b'], info['felica']), ('Yes',) * 3)
        self.assertEqual(parse_info('nfc_open failed')['status'], 'Unavailable')
        self.assertEqual(parse_info(OUTPUT.replace('PN532 v1.6', 'PN533 v2.1'))['model'], 'PN533')

    def test_shared_background_identity_is_cached_without_ui_io(self):
        pd = printer(snapshot())
        reader = pd._rfid_reader
        core = Mock()
        core.get_reader_info.return_value = parse_info(OUTPUT)
        core.get_capabilities.return_value = {'ndef_uri_emulation': True}
        core.get_status.return_value = 'Listening'
        core.get_last_card.return_value = {}
        with patch.object(pd, 'get_nfc_core', return_value=core):
            self.assertTrue(pd.sync_nfc_event())
            self.assertEqual(pd.system_info['nfc']['firmware'], '1.6')
            self.assertEqual(pd.system_info['nfc']['ndef_uri'], 'Yes')
            self.assertFalse(pd.sync_nfc_event())
        reader.identity.assert_not_called()
        reader.snapshot.assert_not_called()

    def test_disabled_feature_reports_status_without_spawning_reader(self):
        pd = printer(snapshot())
        pd._rfid_reader = None
        globals_ = pd.get_nfc_core.__func__.__globals__
        factory = Mock()
        with patch.dict(globals_, {'installed_enabled': lambda: False,
                                   'RFIDReader': factory}):
            self.assertTrue(pd.sync_nfc_event())
            self.assertEqual(pd.system_info['nfc'], {'status': 'Disabled'})
            self.assertEqual(pd.system_info['rfid'], {'status': 'Disabled', 'card': {}})
            self.assertFalse(pd.sync_nfc_event())
            factory.assert_not_called()
            from nfc_settings import NFCSettings
            with self.assertRaisesRegex(OSError, 'disabled'):
                pd.test_nfc_connection(NFCSettings('PN532', 'UART',
                                                   '/dev/ttyAMA0', 115200))
            factory.assert_not_called()

    def test_info_section_and_rows_use_actual_device_values(self):
        view = display(snapshot())
        view.pd.system_info['nfc'] = dict(parse_info(OUTPUT), ndef_uri='Yes')
        items = view._info_items()
        self.assertIn(('section', 'NFC', None), items)
        self.assertIn(('row', 'Model', 'PN532'), items)
        self.assertIn(('row', 'Firmware', '1.6'), items)
        self.assertIn(('row', 'NDEF URI share', 'Yes'), items)
        view.pd.system_info['nfc'] = {'status': 'Unavailable'}
        self.assertNotIn(('row', 'Firmware', '1.6'), view._info_items())
