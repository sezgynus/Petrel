"""Spoolman API, conflict handling and NFC Core enrollment regressions."""
from concurrent.futures import Future
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock

from nfc_core import NFCCore
from spoolman_tags import SpoolmanTags, BindingConflict, describe, tag_uid, colors
from test_nfc_core import backend
from test_capabilities import display, snapshot


def spool(sid=7, uid=None, **changes):
    raw = {'id': sid, 'filament': {'name': 'Galaxy Red', 'material': 'PLA',
           'vendor': {'name': 'Example Filaments'}, 'color_hex': 'FF0022'},
           'extra': {'other': '"keep"'}, 'archived': False}
    if uid:
        raw['extra']['nfc_id'] = json.dumps(uid)
    raw.update(changes)
    return raw


class ServiceTests(unittest.TestCase):
    def service(self, raw=None, other=None, fields=None):
        raw = raw or spool()
        client = Mock()
        database = {item['id']: item for item in [raw] + (other or [])}
        def request(method, endpoint, payload):
            self.assertEqual((method, endpoint), ('POST', '/server/spoolman/proxy'))
            action, path = payload['request_method'], payload['path']
            if action == 'GET' and path.startswith('/v1/spool/'):
                result = database[int(path.rsplit('/', 1)[1])].copy()
            elif action == 'GET' and path == '/v1/spool':
                result = [raw] + (other or [])
            elif action == 'GET' and path == '/v1/field/spool':
                result = fields if fields is not None else []
            elif action == 'POST' and path == '/v1/field/spool/nfc_id':
                self.assertEqual(payload['body']['field_type'], 'text')
                result = [{'key': 'nfc_id', 'field_type': 'text'}]
            elif action == 'PATCH':
                self.assertEqual(payload['body'].keys(), {'extra'})
                self.assertEqual(payload['body']['extra'].keys(), {'nfc_id'})
                target = database[int(path.rsplit('/', 1)[1])]
                target['extra'].update(payload['body']['extra'])
                result = target
            else:
                raise AssertionError(payload)
            return {'result': result}
        client.request.side_effect = request
        return SpoolmanTags(client), client, raw

    def test_confirmed_assignment_is_server_persisted_and_other_fields_preserved(self):
        service, client, raw = self.service()
        expected = describe(raw)
        self.assertEqual(service.assign(7, 'aa bb cc dd', expected), 'AA:BB:CC:DD')
        self.assertEqual(tag_uid(raw), 'AA:BB:CC:DD')
        self.assertEqual(raw['extra']['other'], '"keep"')
        self.assertEqual(describe(raw), expected)
        writes = [c.args[2] for c in client.request.call_args_list
                  if c.args[2]['request_method'] == 'PATCH']
        self.assertEqual(len(writes), 1)

    def test_conflicting_tag_in_archived_spool_and_existing_tag_are_not_overwritten(self):
        for raw, others in ((spool(), [spool(8, 'aa:bb', archived=True)]),
                            (spool(uid='01:02'), [])):
            with self.subTest(raw=raw):
                service, client, raw = self.service(raw, others)
                with self.assertRaises(ValueError):
                    service.assign(7, 'AA:BB', describe(raw))
                self.assertFalse(any(c.args[2]['request_method'] in ('POST', 'PATCH')
                                     for c in client.request.call_args_list))

    def test_incompatible_field_or_changed_spool_fails_closed(self):
        service, client, raw = self.service(fields=[{'key': 'nfc_id', 'field_type': 'integer'}])
        with self.assertRaises(ValueError):
            service.assign(7, '01:02', describe(raw))
        self.assertFalse(any(c.args[2]['request_method'] == 'PATCH' for c in client.request.call_args_list))
        service, client, raw = self.service()
        expected = describe(raw)
        raw['filament'] = dict(raw['filament'], material='PETG')
        with self.assertRaisesRegex(ValueError, 'changed'):
            service.assign(7, '01:02', expected)
        self.assertEqual(client.request.call_count, 1)

    def test_pagination_metadata_and_multicolor(self):
        client = Mock()
        client.request.return_value = {'result': [spool(i + 1) for i in range(21)]}
        service = SpoolmanTags(client)
        rows, more = service.page(20)
        self.assertEqual(len(rows), 20)
        self.assertTrue(more)
        self.assertIn('offset=20', client.request.call_args.args[2]['query'])
        self.assertEqual((rows[0].vendor, rows[0].name, rows[0].material),
                         ('Example Filaments', 'Galaxy Red', 'PLA'))
        self.assertEqual(colors('FF0000AA,00FF00,#0000FF'), ('FF0000', '00FF00', '0000FF'))
        self.assertEqual(colors('garbage'), ())
        self.assertTrue(describe(spool(archived=True)).archived)

    def test_write_error_is_not_replayed_or_reported_as_success(self):
        service, client, raw = self.service()
        original = client.request.side_effect
        def fail(method, endpoint, payload):
            if payload['request_method'] == 'PATCH':
                raise OSError('ambiguous connection loss')
            return original(method, endpoint, payload)
        client.request.side_effect = fail
        with self.assertRaises(OSError):
            service.assign(7, '01:02', describe(raw))
        self.assertEqual(sum(c.args[2]['request_method'] == 'PATCH'
                             for c in client.request.call_args_list), 1)


    def test_conflicting_uid_moves_only_after_fresh_matching_approval(self):
        old = spool(8, 'AA:BB', archived=True)
        service, client, raw = self.service(other=[old])
        expected = describe(raw)
        with self.assertRaises(BindingConflict) as found:
            service.assign(7, 'AA:BB', expected)
        plan = found.exception.plan
        self.assertEqual([item.id for item in plan.sources], [8])
        self.assertEqual(tag_uid(old), 'AA:BB')
        self.assertIsNone(tag_uid(raw))
        self.assertEqual(service.assign(7, 'AA:BB', expected, approval=plan), 'AA:BB')
        self.assertIsNone(tag_uid(old))
        self.assertEqual(tag_uid(raw), 'AA:BB')
        writes = [c.args[2]['path'] for c in client.request.call_args_list
                  if c.args[2]['request_method'] == 'PATCH']
        self.assertEqual(writes, ['/v1/spool/8', '/v1/spool/7'])

    def test_move_approval_cannot_authorize_changed_target_tag(self):
        old = spool(8, 'AA:BB')
        service, client, raw = self.service(other=[old])
        expected = describe(raw)
        with self.assertRaises(BindingConflict) as found:
            service.assign(7, 'AA:BB', expected)
        raw['extra']['nfc_id'] = json.dumps('01:02')
        with self.assertRaises(BindingConflict):
            service.assign(7, 'AA:BB', expected, approval=found.exception.plan)
        self.assertEqual(tag_uid(old), 'AA:BB')
        self.assertFalse(any(c.args[2]['request_method'] == 'PATCH' for c in client.request.call_args_list))


class SpoolUITests(unittest.TestCase):
    def press(self, view, selection):
        view._spool_selection = selection
        view._spool_input(view.ENCODER_DIFF_ENTER)

    def test_async_catalogue_capture_confirm_and_saved_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = backend()
            stop = Mock(return_value=Future())
            core = NFCCore(reader, emergency_stop=stop,
                           actions_file=Path(tmp) / 'actions.json')
            view = display(snapshot())
            view.pd.get_nfc_core = Mock(return_value=core)
            view._queue_nfc_ui_event = Mock()
            view._uart_online = True
            view.checkkey = view.RFIDMenu
            view.Draw_RFID_Menu = Mock()
            page = Future()
            view.pd.nfc_spool_page = Mock(return_value=page)
            view.pd.nfc_assign_spool = Mock(return_value=Future())
            view._spool_load()
            self.assertEqual(view._rfid_mode, 'spool_loading')
            selected = describe(spool())
            page.set_result(((selected,), False))
            view._spool_result_event()
            self.assertEqual(view._rfid_mode, 'spool_list')
            self.press(view, 1)
            self.assertEqual(view._rfid_mode, 'spool_detail')
            self.press(view, 1)
            self.assertEqual(view._rfid_mode, 'spool_waiting')
            emit = reader.set_event_sink.call_args.args[0]
            emit('card.detected', {'uid': 'AA:BB:CC:DD'})
            view._rfid_assignment_event()
            self.assertEqual(view._rfid_mode, 'spool_confirm')
            view.pd.nfc_assign_spool.assert_not_called()
            self.press(view, 1)
            view.pd.nfc_assign_spool.assert_called_once_with(selected, 'AA:BB:CC:DD')
            view.pd.nfc_assign_spool.return_value.set_result('AA:BB:CC:DD')
            view._spool_result_event()
            self.assertEqual(view._rfid_mode, 'spool_saved')
            stop.assert_not_called()
            core.close()

    def test_spool_preview_shows_required_metadata_and_color_below_actions(self):
        view = display(snapshot())
        view._spool_selected = describe(spool())
        view._rfid_candidate = {'uid': ':'.join('%02X' % i for i in range(32))}
        view._draw_list_menu = Mock()
        view._draw_menu_text = Mock()
        for mode in ('spool_detail', 'spool_waiting', 'spool_confirm'):
            view._rfid_mode = mode
            view._draw_menu_text.reset_mock()
            view._spool_draw()
            texts = [c.args[0] for c in view._draw_menu_text.call_args_list]
            for value in ('#7  PLA', 'Example Filaments', 'Galaxy Red', 'Color #FF0022'):
                self.assertIn(value, texts)
            self.assertTrue(all(c.args[2] + 16 < view.STATUS_Y
                                for c in view._draw_menu_text.call_args_list))
        view.lcd.draw_rectangle.assert_any_call(1, 0xF804, 230, 216, 257, 234)

    def test_cancel_capture_does_not_save_and_emergency_still_preempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = backend()
            stop = Mock(return_value=Future())
            core = NFCCore(reader, emergency_stop=stop,
                           actions_file=Path(tmp) / 'actions.json')
            core.assign_global_action('emergency_stop', '01:02')
            view = display(snapshot())
            view.checkkey = view.RFIDMenu
            view._rfid_mode = 'spool_detail'
            view._spool_selected = describe(spool())
            view.pd.get_nfc_core = Mock(return_value=core)
            view.pd.nfc_assign_spool = Mock()
            view.Draw_RFID_Menu = Mock()
            view._queue_nfc_ui_event = Mock()
            self.press(view, 1)
            pending = view._rfid_assignment
            reader.set_event_sink.call_args.args[0]('card.detected', {'uid': '01:02'})
            stop.assert_called_once()
            self.assertFalse(pending.done())
            self.press(view, 0)
            self.assertTrue(pending.cancelled())
            view.pd.nfc_assign_spool.assert_not_called()
            core.close()

    def test_transfer_dialog_requires_separate_explicit_confirmation(self):
        from spoolman_tags import BindingPlan
        selected = describe(spool())
        old = describe(spool(8, 'AA:BB'))
        plan = BindingPlan(selected, 'AA:BB', None, (old,))
        view = display(snapshot())
        view.checkkey = view.RFIDMenu
        view._uart_online = True
        view._rfid_mode = 'spool_saving'
        view._spool_selected = selected
        view._rfid_candidate = {'uid': 'AA:BB'}
        first = Future()
        view._spool_future = first
        view.Draw_RFID_Menu = Mock()
        view._queue_nfc_ui_event = Mock()
        view.pd.nfc_assign_spool = Mock(return_value=Future())
        # The shared UI fixture can retain an earlier module instance after
        # import-isolation tests reload optional modules. Raise the exact
        # exception class used by this view's real handler.
        conflict = view._spool_result_event.__func__.__globals__['BindingConflict']
        first.set_exception(conflict(plan))
        view._spool_result_event()
        self.assertEqual(view._rfid_mode, 'spool_transfer')
        view.pd.nfc_assign_spool.assert_not_called()
        view._draw_list_menu = Mock()
        view._draw_menu_text = Mock()
        view._spool_draw()
        texts = [c.args[0] for c in view._draw_menu_text.call_args_list]
        self.assertIn('From #8', texts)
        self.assertIn('To #7 Example Filaments', texts)
        self.press(view, 1)
        view.pd.nfc_assign_spool.assert_called_once_with(selected, 'AA:BB', approval=plan)
