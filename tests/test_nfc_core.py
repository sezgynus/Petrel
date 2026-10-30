"""NFC Core event, priority, operation and persistence contracts."""
from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from petrel.features.nfc.core import NFCCore, normalize_uid


def backend():
    reader = Mock()
    reader.identity.return_value = {'status': 'Connected'}
    reader.snapshot.return_value = (0, 'Listening', {})
    reader.capabilities.return_value = {'target_mode': True,
                                        'ndef_uri_emulation': True}
    return reader


class CoreTests(unittest.TestCase):
    def make(self, directory, action=None):
        reader = backend()
        core = NFCCore(reader, emergency_stop=action,
                       actions_file=Path(directory) / 'actions.json')
        return core, reader

    def test_global_emergency_preempts_assignment_scope_without_ui_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            emergency = Mock(return_value=Future())
            core, reader = self.make(tmp, emergency)
            core.assign_global_action('emergency_stop', 'AA BB CC DD')
            assignment = Mock(return_value=True)
            ordinary = Mock()
            core.subscribe('card.detected', assignment, priority=100,
                           scope='tag_assignment')
            core.subscribe('card.detected', ordinary, priority=10)
            core.set_context('tag_assignment')
            reader.set_event_sink.call_args.args[0](
                'card.detected', {'uid': 'aa:bb:cc:dd'})
            emergency.assert_called_once_with()
            assignment.assert_not_called()
            ordinary.assert_not_called()
            self.assertEqual(core.get_last_card()['uid'], 'aa:bb:cc:dd')
            core.close()

    def test_assignment_scope_consumes_normal_event_and_can_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, reader = self.make(tmp)
            assignment = Mock(return_value=True)
            normal = Mock()
            core.subscribe('card.detected', normal, priority=10)
            token = core.subscribe('card.detected', assignment, priority=100, scope='assign')
            cb = reader.set_event_sink.call_args.args[0]
            core.set_context('assign')
            cb('card.detected', {'uid': '01:02'})
            assignment.assert_called_once()
            normal.assert_not_called()
            core.unsubscribe(token)
            core.set_context(None)
            cb('card.detected', {'uid': '03:04'})
            normal.assert_called_once()
            cb('card.removed', {'uid': '03:04'})
            self.assertIsNone(core.get_current_card())
            self.assertEqual(core.get_last_card()['uid'], '03:04')
            core.close()

    def test_capability_changes_and_share_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, reader = self.make(tmp)
            cb = reader.set_event_sink.call_args.args[0]
            cb('capabilities.changed',
               {'target_mode': False, 'ndef_uri_emulation': False})
            self.assertFalse(core.get_capabilities()['ndef_uri_emulation'])
            seen = []
            core.subscribe('share.ndef_transferred', lambda payload: seen.append(payload))
            cb('share.ndef_transferred', {'url': 'https://example.org'})
            self.assertEqual(len(seen), 1)
            f = Future()
            reader.share_ndef_uri.return_value = f
            self.assertIs(core.share_ndef_uri('https://example.org'), f)
            f.set_result(True)
            core.cancel_share()
            reader.cancel_share.assert_called_once()
            core.close()

    def test_reader_services_are_mediated_by_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            serial_future = Future()
            serial = Mock(return_value=serial_future)
            reader = backend()
            core = NFCCore(reader, serial_devices=serial,
                           actions_file=Path(tmp) / 'actions.json')
            self.assertIs(core.discover_devices('PN532', 'UART'), serial_future)
            serial.assert_called_once_with()
            reader.discover_devices.assert_not_called()
            discovered = Future()
            reader.discover_devices.return_value = discovered
            self.assertIs(core.discover_devices('PN53x USB', 'USB'), discovered)
            reader.discover_devices.assert_called_once_with('PN53x USB', 'USB')
            reader.test_connection.return_value = Future()
            settings = object()
            self.assertIs(core.test_connection(settings), reader.test_connection.return_value)
            reader.test_connection.assert_called_once_with(settings)
            reader.reload_configuration.return_value = True
            self.assertTrue(core.reload_configuration())
            reader.reload_configuration.assert_called_once_with()
            with self.assertRaises(ValueError):
                core.discover_devices('PN532', 'NCI')
            core.close()

    def test_actions_round_trip_and_invalid_uid(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, reader = self.make(tmp)
            core.assign_global_action('emergency_stop', 'aa:bb:cc:dd')
            self.assertEqual(normalize_uid('aa bb cc dd'), 'AA:BB:CC:DD')
            core.close()
            restored, _ = self.make(tmp)
            self.assertEqual(restored._global_actions['AA:BB:CC:DD'], 'emergency_stop')
            restored.remove_global_action('emergency_stop')
            self.assertFalse(restored._global_actions)
            with self.assertRaises(ValueError):
                restored.assign_global_action('arbitrary_gcode', '01:02')
            restored.close()

    def test_assignment_requires_fresh_arrival_and_explicit_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            emergency = Mock(return_value=Future())
            core, reader = self.make(tmp, emergency)
            emit = reader.set_event_sink.call_args.args[0]
            emit('card.detected', {'uid': '01:02'})
            pending = core.begin_assignment()
            self.assertFalse(pending.done())
            with self.assertRaises(OSError):
                core.begin_assignment()
            emit('card.detected', {'uid': 'aa bb cc dd', 'type': 'ISO14443A'})
            self.assertEqual(pending.result()['uid'], 'AA:BB:CC:DD')
            self.assertIsNone(core.global_action_uid('emergency_stop'))
            emergency.assert_not_called()
            core.assign_global_action('emergency_stop', pending.result()['uid'])
            self.assertEqual(core.global_action_uid('emergency_stop'), 'AA:BB:CC:DD')
            waiting = core.begin_assignment()
            emit('card.detected', {'uid': 'AA:BB:CC:DD'})
            emergency.assert_called_once_with()
            self.assertFalse(waiting.done(), 'Saved EMG tag must preempt enrollment')
            waiting.cancel()
            emit('card.detected', {'uid': '05:06'})
            self.assertTrue(waiting.cancelled())
            core.close()

    def test_failed_save_preserves_previous_tag_and_close_cancels_enrollment(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, _ = self.make(tmp)
            core.assign_global_action('emergency_stop', '01:02')
            with patch.object(core, '_save_actions', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    core.assign_global_action('emergency_stop', '03:04')
            self.assertEqual(core.global_action_uid('emergency_stop'), '01:02')
            pending = core.begin_assignment()
            core.close()
            self.assertTrue(pending.cancelled())
