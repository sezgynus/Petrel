import unittest
from unittest.mock import Mock, patch

from rfid_reader import RFIDReader
from libnfc_api import Target, decode_target
from test_capabilities import display, printer, snapshot


class RFIDTests(unittest.TestCase):
    def test_worker_keeps_one_session_and_scans_every_advertised_type(self):
        with patch('rfid_reader.Thread'):
            reader = RFIDReader()
        session = Mock()
        session.identity.return_value = {'status': 'Connected', 'model': 'PN532'}
        session.modulations = [(kind, 1) for kind in range(1, 11)]
        seen = []
        def scan(modulation):
            seen.append(modulation)
            if len(seen) == 38:
                reader._stop.set()
            return {'uid': '01:02:03:04', 'type': 'ISO14443A'} if modulation[0] == 1 else None
        session.scan.side_effect = scan
        with patch('rfid_reader.NFCSession', return_value=session) as factory:
            reader._run()
            factory.assert_called_once()
        expected = [(1, 1)]
        for modulation in session.modulations[1:]:
            expected.extend([(1, 1), modulation])
        self.assertEqual(seen, expected * 2)
        self.assertEqual([m for m in seen if m != (1, 1)], session.modulations[1:] * 2)
        self.assertEqual(reader.snapshot()[2]['uid'], '01:02:03:04')
        session.close.assert_called_once()

    def test_fast_revisit_follows_last_successful_non_type_a_card(self):
        with patch('rfid_reader.Thread'):
            reader = RFIDReader()
        session = Mock()
        session.identity.return_value = {'status': 'Connected'}
        session.modulations = [(1, 1), (3, 1), (7, 2), (8, 1)]
        seen = []
        def scan(modulation):
            seen.append(modulation)
            if len(seen) >= 18:
                reader._stop.set()
            if modulation == (7, 2):
                return {'uid': '01:02', 'type': 'FeliCa'}
            return None
        session.scan.side_effect = scan
        with patch('rfid_reader.NFCSession', return_value=session):
            reader._run()
        first = seen.index((7, 2))
        self.assertIn((8, 1), seen[first:])
        self.assertIn((3, 1), seen[first:])
        # Once FeliCa is learned, at most one other scan separates its turns.
        positions = [i for i, m in enumerate(seen) if m == (7, 2)]
        self.assertTrue(all(b - a <= 2 for a, b in zip(positions, positions[1:])))

    def test_fast_rfid_tick_updates_card_without_running_full_status_cycle(self):
        import time
        view = display(snapshot())
        view._loop = Mock()
        view._uart_online = True
        view._power_hold_tick = Mock(return_value=False)
        view._power_popup_tick = Mock(return_value=False)
        view._boot_active = False
        view._next_uart_probe = time.monotonic() + 100
        view._rfid_status_at = time.monotonic() + 100
        view._poll_panel_power = Mock()
        view._sync_case_light_tracking = Mock()
        view._poll_rfid_ui = Mock()
        view.EachMomentUpdate = Mock()
        view.checkkey = view.RFIDMenu
        view._ui_tick_body()
        view._loop.set_interval.assert_called_with(.05)
        view._poll_rfid_ui.assert_called_once()
        view.EachMomentUpdate.assert_not_called()

    def test_ready_recovery_tick_keeps_rfid_open_and_still_exits_recovery(self):
        from types import SimpleNamespace
        view = display(snapshot())
        view.pd.connection_error = None
        view.pd.recovery = Mock(state=SimpleNamespace(kind='ready'))
        view.Goto_MainMenu = Mock()
        view.checkkey = view.RFIDMenu
        self.assertNotEqual(view.RFIDMenu, view.RecoveryScreen)
        for _ in range(3):
            self.assertFalse(view._poll_recovery_ui())
            self.assertEqual(view.checkkey, view.RFIDMenu)
        view.Goto_MainMenu.assert_not_called()
        view.checkkey = view.RecoveryScreen
        self.assertFalse(view._poll_recovery_ui())
        view.Goto_MainMenu.assert_called_once()

    def test_all_card_families_decode_their_native_identifiers(self):
        fields = {1: 'a', 2: 'jewel', 3: 'b', 4: 'bi', 5: 'sr', 6: 'ct',
                  7: 'felica', 8: 'dep', 10: 'iclass'}
        for kind, field in fields.items():
            target = Target()
            target.modulation.kind = kind
            target.modulation.baud = 1
            item = getattr(target.info, field)
            if kind == 1:
                item.uid_len = 4
            item.uid[0] = 0xAB
            card = decode_target(target)
            self.assertTrue(card['uid'].startswith('AB:'), kind)
            self.assertNotEqual(card['type'], 'Unknown')
        target = Target()
        target.modulation.kind = 9
        target.info.barcode.length = 32
        self.assertEqual(len(decode_target(target)['uid'].split(':')), 32)
        target.info.barcode.length = 33
        with self.assertRaises(ValueError):
            decode_target(target)

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
        del pd._rfid_reader
        pd.system_info['nfc'] = {'status': 'Connected'}
        factory = Mock()
        with patch.dict(pd.refresh_nfc_info.__func__.__globals__, RFIDReader=factory):
            factory.return_value.identity.return_value = {'status': 'Connected'}
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
        self.assertIn('00:01:02:03:04:05:06:07:08:09', texts)
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
