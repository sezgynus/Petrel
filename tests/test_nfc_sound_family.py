"""Related NFC read, spool-match and confirmed-share cues on existing events."""
from unittest import TestCase
from unittest.mock import Mock
from petrel.features.buzzer.melodies import get_melody
from petrel.ui.events import InputEvent


class NFCSoundFamilyTests(TestCase):
    def test_three_scores_share_read_signature_but_resolve_differently(self):
        read = get_melody('NFC_TAG_READ')
        spool = get_melody('NFC_SPOOL_MATCH')
        share = get_melody('NFC_SHARE_DONE')
        self.assertEqual(spool[:len(read)],read)
        self.assertEqual(share[:len(read)],read)
        self.assertLess(sum(t for _,t in read), .2)
        self.assertLess(sum(t for _,t in read),sum(t for _,t in spool))
        self.assertLess(sum(t for _,t in spool),sum(t for _,t in share))
        self.assertLess(sum(t for _,t in share), .6)
        self.assertEqual(len({read,spool,share}),3)

    def test_spool_match_sound_follows_existing_consumed_lookup_result(self):
        from test_nfc_gate_assignment import GateUITests
        from test_nfc_spool_tags import spool
        from petrel.features.spoolman.tags import describe
        view,_ = GateUITests().make()
        view._event_buzzer_melody = Mock()
        view._nfc_spool_router.take_result.side_effect = [('AA:BB',describe(spool(17))),None]
        view._nfc_gate_result()
        view._nfc_gate_result()
        view._event_buzzer_melody.assert_called_once_with('NFC_SPOOL_MATCH')
        view,_ = GateUITests().make()
        view._event_buzzer_melody = Mock()
        view._nfc_spool_router.take_result.return_value = None
        view._nfc_gate_result()
        view._event_buzzer_melody.assert_not_called()

    def test_share_only_sounds_on_the_transfer_event_that_closes_popup(self):
        from test_nfc_share_ui import NFCShareUITests
        for kind,expected in [('nfc_share_done',True),('nfc_share_cancelled',False),('nfc_share_failed',False)]:
            with self.subTest(kind=kind):
                view,_ = NFCShareUITests().screen()
                view._nfc_share_popup = 'waiting'
                view._event_buzzer_melody = Mock()
                view._finish_nfc_share_popup = Mock(side_effect=lambda:setattr(view,'_nfc_share_popup',None))
                view._draw_nfc_share_popup = Mock()
                view._process_input_untraced(InputEvent(kind,0,0,0))
                if expected:
                    view._event_buzzer_melody.assert_called_once_with('NFC_SHARE_DONE')
                    view._finish_nfc_share_popup.assert_called_once()
                    view._process_input_untraced(InputEvent(kind,0,0,0))
                    self.assertEqual(view._event_buzzer_melody.call_count,1)
                else:
                    view._event_buzzer_melody.assert_not_called()

    def test_all_family_cues_use_same_global_volume_and_mute(self):
        from test_buzzer_events import MelodyOwnerTests
        from test_regressions import ui
        view = MelodyOwnerTests().make()
        view._event_buzzer_ready = True
        view._rfid_buzzer_feedback()
        view._event_buzzer_melody('NFC_SPOOL_MATCH')
        view._event_buzzer_melody('NFC_SHARE_DONE')
        self.assertEqual([c.args[0] for c in view._buzzer_player.play_melody.call_args_list],
                         ['NFC_TAG_READ','NFC_SPOOL_MATCH','NFC_SHARE_DONE'])
        self.assertTrue(all(c.args[1].volume==30 for c in view._buzzer_player.play_melody.call_args_list))
        for settings in (ui.BuzzerSettings(enabled=False),ui.BuzzerSettings(volume=0)):
            view._buzzer_player.reset_mock()
            view._buzzer_values = settings
            view._rfid_buzzer_feedback()
            view._event_buzzer_melody('NFC_SPOOL_MATCH')
            view._event_buzzer_melody('NFC_SHARE_DONE')
            view._buzzer_player.play_melody.assert_not_called()

    def test_arrival_waits_for_lookup_and_plays_exactly_one_selected_cue(self):
        from concurrent.futures import Future
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from petrel.features.nfc.core import NFCCore
        from petrel.features.nfc.spool_router import NFCSpoolRouter
        from test_nfc_core import backend
        from test_nfc_gate_assignment import GateUITests
        from test_nfc_spool_tags import spool
        from petrel.features.spoolman.tags import describe
        for outcome, expected in ((describe(spool(17)), 'NFC_SPOOL_MATCH'),
                                  (None, 'NFC_TAG_READ'),
                                  (OSError('offline'), 'NFC_TAG_READ')):
            for muted in (False, True):
                with self.subTest(expected=expected, muted=muted), TemporaryDirectory() as folder:
                    view, _ = GateUITests().make()
                    view._closed = False
                    view._buzzer_load_complete = view._sound_event_prefs_ready = True
                    view._event_buzzer_ready = True
                    view._event_sound_values = view._event_sound_settings()
                    if muted:
                        view._event_sound_values = view._event_sound_values.toggled(expected)
                    view._buzzer_player = Mock()
                    reader = backend()
                    core = NFCCore(reader, actions_file=Path(folder)/'actions.json')
                    pending = Future()
                    lookup = Mock(return_value=pending)
                    ready = Mock()
                    router = NFCSpoolRouter(core, lookup, ready)
                    view._nfc_spool_router = router
                    view._queue_nfc_ui_event = Mock()
                    view._subscribe_nfc_card_notifications(core)
                    view._nfc_share_component = Mock()
                    view._nfc_share_component.return_value.sync.return_value = False
                    view.pd.sync_nfc_event = Mock()
                    reader.set_event_sink.call_args.args[0]('card.detected', {'uid':'AA:BB'})
                    view._process_input_untraced(InputEvent('nfc_card',0,0,0))
                    view._buzzer_player.play_melody.assert_not_called()
                    if isinstance(outcome, Exception):
                        pending.set_exception(outcome)
                    else:
                        pending.set_result(outcome)
                    ready.assert_called_once()
                    view._nfc_gate_result()
                    view._nfc_gate_result()
                    sounds = [c.args[0] for c in view._buzzer_player.play_melody.call_args_list]
                    self.assertEqual(sounds, [] if muted else [expected])
                    lookup.assert_called_once_with('AA:BB')
                    self.assertEqual(bool(getattr(view, '_nfc_gate_popup', None)),
                                     expected == 'NFC_SPOOL_MATCH')
                    router.close()
                    core.close()
