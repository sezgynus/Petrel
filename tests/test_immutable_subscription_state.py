import copy
from concurrent.futures import Future
import threading
import unittest
from unittest.mock import Mock, patch

from petrel.moonraker.subscription import MoonrakerSubscription
from petrel.printer.state import PrinterState


class ImmutableSubscriptionStateTests(unittest.TestCase):
    def test_printer_update_uses_immutable_path_and_receives_live_delta(self):
        from test_capabilities import printer, snapshot
        data = snapshot()
        owner = printer(data)
        sub = MoonrakerSubscription('http://127.0.0.1:7125', autostart=False)
        sub._settings = copy.deepcopy(data['settings'])
        sub._objects = list(data['objects'])
        sub._epoch = data['epoch']
        sub._state, sub._error = 'ready', None
        sub._merge(data['status'], 1, replace=True)
        sub._merge({'extruder': {'temperature': 47}}, 2)
        # Keep every other transport/worker fixture unchanged; only replace the
        # UI state read functions with the production subscription's API.
        owner.subscription._supports_immutable_state = True
        owner.subscription.lifecycle.side_effect = sub.lifecycle
        owner.subscription.immutable_state.side_effect = sub.immutable_state
        owner.subscription.snapshot.reset_mock()
        owner.update_variable()
        owner.subscription.immutable_state.assert_called_once_with()
        self.assertEqual(owner.state.status['extruder']['temperature'], 47)
        owner.subscription.snapshot.assert_not_called()

    def make(self):
        sub = MoonrakerSubscription('http://127.0.0.1:7125', autostart=False)
        sub._state, sub._error = 'ready', None
        sub._settings = {'extruder': {'max_temp': 300},
                         'heater_generic chamber': {'heater_pin': 'PA1'}}
        sub._objects = ['extruder', 'toolhead', 'heater_generic chamber',
                        'output_pin case_light']
        sub._merge({'extruder': {'temperature': 20, 'target': 0},
                    'toolhead': {'position': [1, 2, 3, 4],
                                 'nested': {'values': [5, 6]}}}, 1, replace=True)
        return sub

    def test_values_match_legacy_state_without_deepcopy_on_read(self):
        sub = self.make()
        expected = PrinterState.from_snapshot(sub.snapshot())
        with patch.object(copy, 'deepcopy', side_effect=AssertionError('read copied mutable tree')):
            self.assertEqual(sub.immutable_state(), expected)

    def test_delta_shares_only_unchanged_objects_and_settings(self):
        sub = self.make()
        old = sub.immutable_state()
        sub._merge({'extruder': {'temperature': 25}}, 2)
        new = sub.immutable_state()
        self.assertIs(old.status['toolhead'], new.status['toolhead'])
        self.assertIs(old.settings, new.settings)
        self.assertIsNot(old.status['extruder'], new.status['extruder'])
        self.assertEqual(old.status['extruder']['temperature'], 20)
        self.assertEqual(new.status['extruder']['temperature'], 25)
        self.assertEqual(new.status['extruder']['target'], 0)

    def test_nested_aliases_cannot_mutate_old_or_new_state(self):
        sub = self.make()
        old = sub.immutable_state()
        legacy = sub.snapshot()
        legacy['status']['toolhead']['position'][0] = 99
        self.assertEqual(old.status['toolhead']['position'][0], 1)
        with self.assertRaises(TypeError):
            old.status['toolhead']['nested']['values'][0] = 9
        with self.assertRaises(TypeError):
            old.settings['extruder']['max_temp'] = 999
        sub._merge({'toolhead': {'position': [9, 8, 7, 6]}}, 2)
        self.assertEqual(old.status['toolhead']['position'], (1, 2, 3, 4))
        self.assertEqual(sub.immutable_state().status['toolhead']['position'], (9, 8, 7, 6))

    def test_replacement_and_disconnect_drop_cached_objects(self):
        sub = self.make()
        old = sub.immutable_state()
        sub._merge({'print_stats': {'state': 'standby'}}, 2, replace=True)
        self.assertEqual(set(sub.immutable_state().status), {'print_stats'})
        self.assertEqual(set(sub._frozen_status), {'print_stats'})
        sub._invalidate('disconnected')
        new = sub.immutable_state()
        self.assertEqual(new.connection, 'disconnected')
        self.assertFalse(new.status)
        self.assertFalse(new.settings)
        self.assertTrue(old.status['toolhead'])
        self.assertEqual(len(sub._frozen_status), 0)

    def test_stale_delta_does_not_invalidate_or_overwrite_state(self):
        sub = self.make()
        old = sub.immutable_state()
        sub._merge({'toolhead': {'position': [99]}}, 0)
        new = sub.immutable_state()
        self.assertIs(new.status['toolhead'], old.status['toolhead'])
        self.assertEqual(new.revision, old.revision)

    def test_optional_thermal_seed_and_prune_invalidate_cached_tree(self):
        sub = self.make()
        sub._usage_fields = {'heater_generic chamber': 'power'}
        sub._merge({'heater_generic chamber': {'power': 0}}, 2)
        old = sub.immutable_state()
        future = Future()
        sub.request = Mock(return_value=future)
        sub.set_thermal_tracking(True)
        future.set_result({'status': {'heater_generic chamber': {
            'temperature': 35, 'target': 40, 'power': .2}}})
        new = sub.immutable_state()
        self.assertEqual(new.status['heater_generic chamber']['temperature'], 35)
        self.assertNotIn('temperature', old.status['heater_generic chamber'])
        sub.request = Mock(return_value=Future())
        sub.set_thermal_tracking(False)
        self.assertEqual(dict(sub.immutable_state().status['heater_generic chamber']), {'power': 0})
        self.assertEqual(new.status['heater_generic chamber']['temperature'], 35)

    def test_case_light_removal_does_not_leave_cached_pin(self):
        sub = self.make()
        sub._case_light_tracking = True
        sub._merge({'output_pin case_light': {'value': .5}}, 2)
        old = sub.immutable_state()
        sub.request = Mock(return_value=Future())
        sub.set_case_light_tracking(False)
        self.assertNotIn('output_pin case_light', sub.immutable_state().status)
        self.assertEqual(old.status['output_pin case_light']['value'], .5)

    def test_concurrent_delta_and_reads_are_coherent_and_history_is_bounded(self):
        sub = self.make()
        failures = []
        def update():
            try:
                for value in range(2, 202):
                    sub._merge({'toolhead': {'position': [value] * 4}}, value)
            except Exception as error:
                failures.append(error)
        thread = threading.Thread(target=update)
        thread.start()
        for _ in range(200):
            state = sub.immutable_state()
            position = state.status['toolhead']['position']
            if position != (1, 2, 3, 4):
                self.assertEqual(position, (position[0],) * 4)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures)
        self.assertEqual(sub.immutable_state().status['toolhead']['position'], (201,) * 4)
        self.assertEqual(len(sub._frozen_status), len(sub._status))


if __name__ == '__main__':
    unittest.main()
