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
            self.assertTrue(any('ASSIGN FILAMENT' in text for text in texts))
            self.assertEqual(len(view._nfc_gate_popup['operations']), 5)
            view.pd.subscription.request.assert_not_called()
            view.pd.sendGCode.assert_not_called()
            view._redraw_current_screen = Mock()
            view._nfc_gate_close()
            self.assertEqual(view.checkkey, getattr(view, origin))

    def test_gate_popup_reuses_shared_mmu_icons_without_redrawing_on_rotate(self):
        from lcd_resources import ICON_SPOOL_EMPTY
        from unittest.mock import patch
        view, _ = self.make()
        view._nfc_gate_result()
        popup = view._nfc_gate_popup
        self.assertEqual(popup['selection'], 0)
        icons = [call.args for call in view.lcd.show_icon.call_args_list
                 if len(call.args) >= 4 and call.args[1] == ICON_SPOOL_EMPTY]
        self.assertEqual(len(icons), 5)  # Four ghost gates + colored moving reel.
        lines = [call.args[-1] for call in view.lcd.draw_text.call_args_list]
        self.assertTrue(any('Example Filament' in line for line in lines))
        self.assertTrue(any('Galaxy Red' in line for line in lines))
        self.assertTrue(any('PLA' in line for line in lines))
        self.assertIsNone(popup['operations'][0])

        view.lcd.reset_mock()
        view._nfc_gate_input(InputEvent('rotate', -1, 1, 0))
        self.assertEqual(popup['selection'], 1)
        # Back->G0 only changes focus: the reel already hovers above G0.
        view._nfc_gate_input(InputEvent('rotate', -1, 1, 0))
        self.assertEqual(popup['selection'], 2)
        self.assertIn('motion', popup)
        view.Clear_Popup_Area = Mock()
        view._nfc_gate_draw = Mock()
        view.lcd.reset_mock()
        start = popup['motion']['start']
        view._nfc_gate_motion_tick(popup, now=start + .175)
        self.assertEqual(view.lcd.move_area.call_count, 2)  # Reel + moving info.
        args = [call.args for call in view.lcd.move_area.call_args_list]
        self.assertTrue(all(a[0] == 1 and a[1] == 1 and a[2] > 0 for a in args))
        self.assertFalse(view.lcd.show_icon.called)
        self.assertFalse(view.Clear_Popup_Area.called)
        self.assertFalse(view._nfc_gate_draw.called)
        self.assertFalse(view.lcd.draw_text.called)

        # Retarget mid-flight; no jumps or catch-up redraw.
        midway = popup['sprite_x']
        view._nfc_gate_input(InputEvent('rotate', -1, 1, 0))
        self.assertEqual(popup['selection'], 3)
        self.assertEqual(popup['sprite_x'], midway)
        view.lcd.reset_mock()
        next_motion = popup['motion']
        view._nfc_gate_motion_tick(popup, now=next_motion['start'] + .35)
        self.assertEqual(popup['sprite_x'], popup['positions'][3])
        self.assertFalse(view.lcd.show_icon.called)
        view.pd.subscription.request.assert_not_called()

    def test_gif_easing_and_timing_match_sampled_motions(self):
        from ui_nfc_gate import NFCGateViewMixin
        ease = NFCGateViewMixin._nfc_gate_ease
        for phase, expected in ((0, 0), (.5, .5), (1, 1)):
            self.assertAlmostEqual(ease(phase), expected, places=9)
        self.assertAlmostEqual(ease(.25), .1464466094, places=8)
        self.assertAlmostEqual(ease(.75), .8535533906, places=8)
        self.assertAlmostEqual(ease(-1), 0)
        self.assertAlmostEqual(ease(5), 1)
        self.assertEqual(NFCGateViewMixin.GATE_TRAVEL_SECONDS, .35)
        self.assertEqual(NFCGateViewMixin.GATE_LANDING_SECONDS, .60)
        self.assertEqual(NFCGateViewMixin.GATE_ANIMATION_INTERVAL, .05)

    def test_verified_landing_moves_existing_pixels_and_does_not_reload_icon(self):
        view, _ = self.make()
        view._nfc_gate_result()
        popup = view._nfc_gate_popup
        view._nfc_gate_input(InputEvent('rotate', -1, 1, 0))
        view._nfc_gate_input(InputEvent('rotate', -1, 1, 0))
        view._nfc_gate_motion_tick(popup, now=popup['motion']['start'] + .36)
        self.assertNotIn('motion', popup)
        popup['operation'] = popup['operations'][1]
        popup['phase'] = 'writing'
        popup['message'] = 'Assigning to G0'
        view.lcd.reset_mock()
        view._nfc_gate_start_vertical(popup, 267)
        view._nfc_gate_motion_tick(popup, now=popup['motion']['start'] + .3)
        self.assertTrue(view.lcd.move_area.called)
        a = view.lcd.move_area.call_args.args
        self.assertEqual(a[:2], (1, 3))  # Native 0x09, down.
        self.assertFalse(view.lcd.show_icon.called)
        self.assertFalse(view.lcd.draw_text.called)
        view._nfc_gate_motion_tick(popup, now=popup['motion']['start'] + .6)
        self.assertEqual(popup['sprite_y'], 267)
        view.lcd.reset_mock()
        view._nfc_gate_start_vertical(popup, view.GATE_GHOST_TOP)
        # Clear the destination ghost just once, not on each moving frame.
        self.assertEqual(view.lcd.draw_rectangle.call_count, 1)
        view.lcd.reset_mock()
        view._nfc_gate_motion_tick(popup, now=popup['motion']['start'] + .6)
        self.assertEqual(popup['sprite_y'], view.GATE_GHOST_TOP)
        self.assertFalse(view.lcd.show_icon.called)
        self.assertFalse(view.lcd.draw_rectangle.called)
        self.assertFalse(view.lcd.draw_text.called)

    def test_popup_uses_native_packet_opcode_09_with_filled_clear_mode(self):
        from test_t5uic1_driver import driver
        from ui_nfc_gate import NFCGateViewMixin
        lcd = driver()
        lcd.move_area(1, 1, 12, NFCGateViewMixin.GATE_BG, 19, 234, 72, 285)
        packet = lcd.serial.frames[-1]
        self.assertEqual(packet[1], 0x09)
        self.assertEqual(packet[2], 0x81)  # mode 1, right.
        self.assertEqual(int.from_bytes(packet[3:5], 'big'), 12)
        self.assertEqual(int.from_bytes(packet[5:7], 'big'), 0x2125)

    def test_back_header_is_cancel_and_never_sends_mmu_command(self):
        view, _ = self.make()
        view._nfc_gate_result()
        self.assertEqual(view._nfc_gate_popup['selection'], 0)
        view._redraw_current_screen = Mock()
        view._nfc_gate_input(InputEvent('press', 1, 1, 0))
        self.assertIsNone(view._nfc_gate_popup)
        self.assertEqual(view.checkkey, view.Info)
        view.pd.subscription.request.assert_not_called()

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

    def test_emergency_during_nested_power_dialog_cannot_restore_a_dead_gate_popup(self):
        view, _ = self.make()
        view._nfc_gate_result()
        view._power_origin = view.NFCGateMenu
        view.checkkey = view.PowerConfirm
        view._nfc_gate_close()
        self.assertIsNone(view._nfc_gate_popup)
        self.assertEqual(view._power_origin, view.Info)
        self.assertEqual(view.checkkey, view.PowerConfirm)
        view.pd.subscription.request.assert_not_called()

    def test_lookup_finishing_under_power_dialog_resumes_after_return(self):
        view, _ = self.make()
        view._nfc_gate_result()
        view._nfc_gate_popup['selection'] = 1
        future = Future()
        view.pd.nfc_lookup_spool = Mock(return_value=future)
        view._nfc_gate_input(InputEvent('press', 1, 1, 0))
        view.checkkey = view.PowerConfirm
        future.set_result(describe(spool(17)))
        view._nfc_gate_verify()
        view.pd.subscription.request.assert_not_called()
        view.checkkey = view.NFCGateMenu
        view._focus_tick_quiet = Mock()
        self.assertTrue(view._nfc_gate_tick())
        self.assertEqual(view._nfc_gate_popup['phase'], 'writing')
        view.pd.subscription.request.assert_called_once()
