"""NFC Info discovery stays asynchronous, scoped and cached."""
from concurrent.futures import Future
import subprocess
import unittest
from unittest.mock import Mock, patch

from nfc_info import DEFAULT_DEVICE, parse_info, read_nfc_info
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

    def test_explicit_device_and_no_autoscan_with_bounded_subprocess(self):
        with patch('nfc_info.shutil.which', return_value='/usr/bin/nfc-scan-device'), \
             patch('nfc_info.Path.exists', return_value=True), \
             patch.dict('os.environ', {'LIBNFC_AUTO_SCAN': 'true'}, clear=True), \
             patch('nfc_info.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, OUTPUT, '')
            self.assertEqual(read_nfc_info()['firmware'], '1.6')
            args, kwargs = run.call_args
            self.assertEqual(args[0], ['/usr/bin/nfc-scan-device', '-v'])
            self.assertEqual(kwargs['env']['LIBNFC_DEVICE'], DEFAULT_DEVICE)
            self.assertEqual(kwargs['env']['LIBNFC_AUTO_SCAN'], 'false')
            self.assertEqual(kwargs['env']['LIBNFC_INTRUSIVE_SCAN'], 'false')
            self.assertEqual(kwargs['timeout'], 4)
            run.side_effect = subprocess.TimeoutExpired('scan', 4)
            self.assertEqual(read_nfc_info()['status'], 'Timed out')

    def test_missing_tool_or_port_does_not_launch_a_scan(self):
        with patch('nfc_info.shutil.which', return_value=None), \
             patch('nfc_info.subprocess.run') as run:
            self.assertEqual(read_nfc_info()['status'], 'libnfc missing')
            run.assert_not_called()
        with patch('nfc_info.shutil.which', return_value='/usr/bin/nfc-scan-device'), \
             patch('nfc_info.Path.exists', return_value=False), \
             patch.dict('os.environ', {}, clear=True), patch('nfc_info.subprocess.run') as run:
            self.assertEqual(read_nfc_info()['status'], 'Unavailable')
            run.assert_not_called()

    def test_pending_read_never_blocks_and_completed_identity_is_cached(self):
        pd = printer(snapshot())
        future = Future()
        pd._read_worker = Mock()
        pd._read_worker.submit.return_value = future
        self.assertFalse(pd.refresh_nfc_info())
        self.assertFalse(pd.refresh_nfc_info())
        pd._read_worker.submit.assert_called_once()
        future.set_result(parse_info(OUTPUT))
        self.assertTrue(pd.refresh_nfc_info())
        self.assertEqual(pd.system_info['nfc']['firmware'], '1.6')
        for _ in range(5):
            self.assertFalse(pd.refresh_nfc_info())
        pd._read_worker.submit.assert_called_once()

    def test_info_section_and_rows_use_actual_device_values(self):
        view = display(snapshot())
        view.pd.system_info['nfc'] = parse_info(OUTPUT)
        items = view._info_items()
        self.assertIn(('section', 'NFC', None), items)
        self.assertIn(('row', 'Model', 'PN532'), items)
        self.assertIn(('row', 'Firmware', '1.6'), items)
        view.pd.system_info['nfc'] = {'status': 'Unavailable'}
        self.assertNotIn(('row', 'Firmware', '1.6'), view._info_items())
