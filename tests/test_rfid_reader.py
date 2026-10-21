import unittest
from unittest.mock import Mock, patch

from rfid_reader import RFIDReader, parse_card_line
from test_capabilities import display, printer, snapshot


class RFIDTests(unittest.TestCase):
    def test_streaming_uid_type_and_metadata_without_guessing_chip(self):
        card = {}
        for line in ('ISO/IEC 14443A (106 kbps) target:',
                     'ATQA (SENS_RES): 00 04', 'UID (NFCID1): 6b b3 9d 14',
                     'SAK (SEL_RES): 08'):
            card = parse_card_line(line, card)
        self.assertEqual(card, {'type': 'ISO14443A', 'rate': '106 kbps',
            'uid': '6B:B3:9D:14', 'atqa': '00 04', 'sak': '08'})
        self.assertEqual(parse_card_line('Waiting for card removing...', card), card)
        self.assertEqual(parse_card_line('UID (NFCID1): nonsense', {}), {})

    def test_reader_retains_last_card_and_caches_unchanged_values(self):
        with patch('rfid_reader.Thread'):
            reader = RFIDReader()
        reader._publish('Listening', {'uid': '01:02:03:04', 'type': 'ISO14443A'})
        first = reader.snapshot()
        reader._publish('Listening')
        self.assertEqual(reader.snapshot(), first)
        copied = reader.snapshot()[2]
        copied['uid'] = 'changed'
        self.assertEqual(reader.snapshot(), first)
        reader._publish('Reader unavailable')
        self.assertEqual(reader.snapshot()[2]['uid'], '01:02:03:04')
        reader.close()

    def test_one_reader_owner_and_changed_card_reaches_ui(self):
        pd = printer(snapshot())
        pd._nfc_info_complete = True
        pd.system_info['nfc'] = {'status': 'Connected'}
        factory = Mock()
        with patch.dict(pd.refresh_rfid.__func__.__globals__, RFIDReader=factory):
            factory.return_value.snapshot.return_value = (1, 'Listening', {'uid': '01:02:03:04'})
            self.assertTrue(pd.refresh_rfid())
            self.assertFalse(pd.refresh_rfid())
            factory.assert_called_once()
            factory.return_value.snapshot.return_value = (2, 'Listening', {'uid': '05:06:07:08'})
            self.assertTrue(pd.refresh_rfid())
            self.assertEqual(pd.system_info['rfid']['card']['uid'], '05:06:07:08')

    def test_menu_entry_return_and_incremental_full_uid(self):
        view = display(snapshot())
        view.pd.refresh_rfid = Mock(return_value=False)
        uid = ':'.join(f'{i:02X}' for i in range(10))
        view.pd.system_info['rfid'] = {'status': 'Listening',
            'card': {'type': 'ISO14443A', 'uid': uid}}
        view.Draw_RFID_Menu()
        texts = [c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertIn('00:01:02:03:04:05:06', texts)
        self.assertIn('07:08:09', texts)
        view.lcd.reset_mock()
        view.Draw_RFID_Menu(full=False)
        view.lcd.draw_text.assert_not_called()
        view.lcd.draw_rectangle.assert_not_called()
        view.checkkey = view.RFIDMenu
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.Goto_MainMenu = Mock()
        view.HMI_RFID()
        self.assertEqual(view._home_entries()[view.select_page.now][0], 'RFID')
        view.Goto_MainMenu.assert_called_once()
