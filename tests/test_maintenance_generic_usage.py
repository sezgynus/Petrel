"""CI regressions for passive metric contracts, inventory and durable usage."""
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace as NS
from maintenance_discovery import discover, NONE
from maintenance_usage import usage_metrics, MAX_TRACKED_METRICS


class UsageContracts(unittest.TestCase):
    def test_inventory_includes_readable_outputs_without_actuation_permission(self):
        names = ('fan', 'heater_fan any', 'controller_fan any', 'fan_generic any',
                 'temperature_fan any', 'extruder', 'extruder2', 'heater_bed',
                 'heater_generic any', 'output_pin arbitrary', 'pwm_cycle_time sound',
                 'pwm_tool spindle')
        state = NS(ready=True, epoch=1, objects=names, settings={}, status={})
        snap = discover(state)
        self.assertEqual({m.device for m in snap.usage_metrics}, set(names))
        self.assertEqual(snap.method('O03', 'output_pin arbitrary'), NONE)
        self.assertEqual(snap.usage_omitted, 0)
        self.assertTrue(all(m.unit == 's' and m.metric_id == 'sampled_on_s'
                            for m in snap.usage_metrics))
        with self.assertRaises(FrozenInstanceError):
            snap.usage_metrics[0].field = 'other'

    def test_unsupported_objects_and_config_only_pins_do_not_create_metrics(self):
        state = NS(ready=True, epoch=1, objects=('servo a', 'stepper_x',
            'gcode_button a', 'filament_switch_sensor a', 'temperature_sensor a'),
            settings={'output_pin absent': {'pin': 'PA1'}}, status={})
        self.assertEqual(discover(state).usage_metrics, ())
        state.ready = False
        self.assertEqual(discover(state).usage_metrics, ())

    def test_contract_survives_missing_initial_sample_but_validates_each_value(self):
        metric = usage_metrics(('output_pin arbitrary',))[0][0]
        for value in (None, True, False, '1', -1, float('nan'), float('inf')):
            self.assertIsNone(metric.active({metric.device: {'value': value}}))
        self.assertIsNone(metric.active({}))
        self.assertIsNone(metric.active({metric.device: []}))
        self.assertIs(metric.active({metric.device: {'value': 0}}), False)
        self.assertIs(metric.active({metric.device: {'value': .3}}), True)

    def test_stable_capacity_preserves_standard_counters_and_reports_excess(self):
        names = ['output_pin p%03d' % i for i in range(100)] + ['fan', 'extruder', 'heater_bed']
        first, omitted = usage_metrics(names)
        self.assertEqual((first, omitted), usage_metrics(reversed(names)))
        self.assertEqual(len(first), MAX_TRACKED_METRICS)
        self.assertEqual(omitted, len(names) - MAX_TRACKED_METRICS)
        self.assertTrue({'fan', 'extruder', 'heater_bed'} <= {m.device for m in first})
        self.assertEqual(usage_metrics(('output_pin ' + 'a'*100,))[0], ())
