"""Global event routing, bounded lookup and guarded gate assignment."""
from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from nfc_core import NFCCore
from nfc_spool_router import NFCSpoolRouter
from spoolman_tags import SpoolmanTags, describe
from ui_events import InputEvent
from test_nfc_core import backend
from test_capabilities import display
from test_mmu_control import mmu_snapshot
from test_nfc_spool_tags import spool


class RouterTests(unittest.TestCase):
    def test_global_card_lookup_and_emergency_enrollment_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = backend()
            stop = Mock(return_value=Future())
            core = NFCCore(reader, emergency_stop=stop,
                           actions_file=Path(tmp) / 'actions.json')
            future = Future()
            lookup, ready = Mock(return_value=future), Mock()
            router = NFCSpoolRouter(core, lookup, ready)
            emit = reader.set_event_sink.call_args.args[0]
            core.set_context('any_screen')
            emit('card.detected', {'uid': 'aa:bb'})
            lookup.assert_called_once_with('AA:BB')
            expected = describe(spool())
            future.set_result(expected)
            self.assertEqual(router.take_result(), ('AA:BB', expected))
            ready.assert_called_once()
            assignment = core.begin_assignment()
            emit('card.detected', {'uid': '03:04'})
            self.assertEqual(assignment.result()['uid'], '03:04')
            lookup.assert_called_once()
            core.assign_global_action('emergency_stop', '01:02')
            emit('card.detected', {'uid': '01:02'})
            stop.assert_called_once()
            lookup.assert_called_once()
            self.assertEqual(router.take_result(), (None, None))
            router.close()
            core.close()

    def test_lookup_retains_only_active_and_latest_arrival(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = backend()
            core = NFCCore(reader, actions_file=Path(tmp) / 'actions.json')
            first, last = Future(), Future()
            lookup = Mock(side_effect=[first, last])
            ready = Mock()
            router = NFCSpoolRouter(core, lookup, ready)
            emit = reader.set_event_sink.call_args.args[0]
            for uid in ('01:02', '03:04', '05:06'):
                emit('card.detected', {'uid': uid})
            self.assertEqual(lookup.call_count, 1)
            first.set_result(describe(spool(1)))
            self.assertIsNone(router.take_result())
            lookup.assert_called_with('05:06')
            last.set_result(describe(spool(3)))
            self.assertEqual(router.take_result()[0], '05:06')
            ready.assert_called_once()
            router.close()
            core.close()

    def test_unknown_uid_does_not_open_popup_and_lookup_has_no_scan_or_activation_write(self):
        client = Mock()
        client.request.return_value = {'result': []}
        self.assertIsNone(SpoolmanTags(client).lookup('AA:BB'))
        payload = client.request.call_args.args[2]
        self.assertEqual(payload['request_method'], 'GET')
        self.assertEqual(payload['path'], '/v1/spool')
        self.assertIn('tag=AABB', payload['query'])


class GateUITests(unittest.TestCase):
    def make(self, **changes):
        data = mmu_snapshot(**changes)
        view = display(data)
        view._closed = False
        view._uart_online = True
        view._update_ui_state = Mock()
        view._display_activity = Mock(return_value=False)
        view._queue_nfc_ui_event = Mock()
        view.checkkey = view.Info
        view.pd.subscription.responses_since.return_value = (0, ())
        view.pd.subscription.request.return_value = Future()
        view._nfc_spool_router = Mock()
        view._nfc_spool_router.take_result.return_value = ('AA:BB', describe(spool(17)))
        return view, data

    def test_any_menu_match_opens_gate_prompt_without_assigning_or_loading(self):
        for origin in ('Info', 'MainMenu', 'Tune', 'RFIDMenu'):
            view, _ = self.make()
            view.checkkey = getattr(view, origin)
            view._nfc_gate_result()
            self.assertEqual(view.checkkey, view.NFCGateMenu)
            self.assertEqual(view._nfc_gate_popup['origin'], getattr(view, origin))
            texts = [call.args[-1] for call in view.lcd.draw_text.call_args_list]
            self.assertIn('Spool #17: choose gate', texts)
            self.assertEqual(len(view._nfc_gate_popup['operations']), 5)
            view.pd.subscription.request.assert_not_called()
            view.pd.sendGCode.assert_not_called()
            view._redraw_current_screen = Mock()
            view._nfc_gate_close()
            self.assertEqual(view.checkkey, getattr(view, origin))

    def test_gate_selection_rechecks_native_binding_then_uses_real_mmu_session(self):
        view, data = self.make()
        view._nfc_gate_result()
        view._nfc_gate_popup['selection'] = 3  # Cancel + gates: index 3 is G2.
        verification = Future()
        view.pd.nfc_lookup_spool = Mock(return_value=verification)
        view._nfc_gate_input(InputEvent('press', 1, 1, 0))
        view.pd.subscription.request.assert_not_called()
        verification.set_result(describe(spool(17)))
        view._nfc_gate_verify()
        self.assertEqual(view._nfc_gate_popup['phase'], 'writing')
        args = view.pd.subscription.request.call_args
        self.assertEqual(args.args[:2], ('printer.gcode.script',
            {'script': 'MMU_GATE_MAP GATE=2 SPOOLID=17 TEMP=215'}))
        self.assertTrue(args.kwargs['guard']())
        data['status']['print_stats']['state'] = 'printing'
        self.assertFalse(args.kwargs['guard']())
        self.assertNotIn('MMU_LOAD', args.args[1]['script'])

    def test_changed_binding_or_gate_snapshot_cannot_dispatch(self):
        for changed_binding in (True, False):
            view, data = self.make()
            view._nfc_gate_result()
            view._nfc_gate_popup['selection'] = 1
            future = Future()
            view.pd.nfc_lookup_spool = Mock(return_value=future)
            view._nfc_gate_input(InputEvent('press', 1, 1, 0))
            if not changed_binding:
                data['status']['mmu']['gate_spool_id'][0] = 888
            future.set_result(None if changed_binding else describe(spool(17)))
            view._nfc_gate_verify()
            self.assertEqual(view._nfc_gate_popup['phase'], 'error')
            view.pd.subscription.request.assert_not_called()

    def test_printing_is_blocked_and_cancel_while_checking_never_assigns(self):
        view, data = self.make()
        data['status']['print_stats']['state'] = 'printing'
        view._nfc_gate_result()
        self.assertEqual(view._nfc_gate_popup['operations'], [None])
        view.pd.subscription.request.assert_not_called()
        view, _ = self.make()
        view._nfc_gate_result()
        view._nfc_gate_popup['selection'] = 1
        future = Future()
        future.set_running_or_notify_cancel()
        view.pd.nfc_lookup_spool = Mock(return_value=future)
        view._nfc_gate_input(InputEvent('press', 1, 1, 0))
        view._redraw_current_screen = Mock()
        view._nfc_gate_close()
        future.set_result(describe(spool(17)))
        view._nfc_gate_verify()
        view.pd.subscription.request.assert_not_called()
