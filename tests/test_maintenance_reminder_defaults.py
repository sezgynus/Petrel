"""CI-only contracts for generic new-reminder starting intervals."""
import unittest
from petrel.features.maintenance.records.care import reminder_default


class ReminderDefaultIntervals(unittest.TestCase):
    def test_axes_and_their_available_travel_have_distinct_intervals(self):
        for axis in ('x', 'y'):
            for device in ('stepper_'+axis, 'axis_'+axis):
                self.assertEqual(reminder_default(device,'mechanical','calendar_s'),90)
                self.assertEqual(reminder_default(device,'mechanical','sampled_print_s'),200)
                self.assertEqual(reminder_default(device,'mechanical','travel_mm'),30000)
        self.assertEqual(reminder_default('stepper_z','mechanical','calendar_s'),180)
        self.assertEqual(reminder_default('stepper_z','mechanical','sampled_print_s'),500)
        self.assertEqual(reminder_default('axis_z','mechanical','travel_mm'),10)
        self.assertEqual(reminder_default('stepper_z1','mechanical','calendar_s'),180)

    def test_sensors_use_configured_object_type_not_custom_name(self):
        cases = (
            ('endstop stepper_x', 180, 500),
            ('endstop stepper_y', 180, 500),
            ('probe', 90, 2000),
            ('bltouch', 90, 2000),
            ('filament_switch_sensor gate_a', 90, 2000),
            ('filament_motion_sensor encoder_a', 90, 50000),
            ('gcode_button user_defined', 180, 1000),
        )
        for device, days, events in cases:
            with self.subTest(device=device):
                self.assertEqual(reminder_default(device,'sensor','calendar_s'),days)
                self.assertEqual(reminder_default(device,'sensor','trigger_count'),events)
                self.assertEqual(reminder_default(device,'sensor','observed_trigger_count'),events)
        self.assertEqual(reminder_default('temperature_sensor chamber','sensor','calendar_s'),365)

    def test_extruder_maintenance_tasks_are_different(self):
        for device in ('extruder','extruder1'):
            self.assertEqual(reminder_default(device,'filament_feed','calendar_s'),90)
            self.assertEqual(reminder_default(device,'filament_feed','sampled_print_s'),200)
            self.assertEqual(reminder_default(device,'nozzle','calendar_s'),30)
            self.assertEqual(reminder_default(device,'nozzle','sampled_print_s'),100)
            self.assertEqual(reminder_default(device,'nozzle','sampled_on_s'),100)
            self.assertEqual(reminder_default(device,'heating','calendar_s'),180)
            self.assertEqual(reminder_default(device,'heating','sampled_on_s'),300)

    def test_fans_lights_heaters_electronics_and_generic(self):
        rows = (
            ('fan', 'fan', (90,200,200)),
            ('fan_generic part', 'fan', (90,200,200)),
            ('heater_bed', 'heating', (180,500,300)),
            ('heater_generic enclosure', 'heating', (180,500,300)),
            ('neopixel lights', 'lighting', (365,500,1000)),
            ('output_pin arbitrary', 'connected_device', (180,500,500)),
            ('output_pin fan', 'connected_device', (180,500,500)),
            ('pwm_cycle_time buzzer', 'connected_device', (180,500,500)),
            ('mcu', 'electronics', (365,700,500)),
            ('tmc2209 stepper_x', 'electronics', (365,700,500)),
            ('servo tool', 'actuator', (180,500,500)),
            ('unrecognized', 'general', (180,500,500)),
        )
        for device, task, (days, print_hours, on_hours) in rows:
            with self.subTest(device=device):
                self.assertEqual(reminder_default(device,task,'calendar_s'),days)
                self.assertEqual(reminder_default(device,task,'sampled_print_s'),print_hours)
                self.assertEqual(reminder_default(device,task,'sampled_on_s'),on_hours)

    def test_unknown_basis_is_rejected_and_values_fit_existing_editor(self):
        with self.assertRaises(ValueError):
            reminder_default('output_pin lamp','connected_device','power_cycles')
        from petrel.features.maintenance.records.care import REMINDER_DEFAULTS, REMINDER_BASIS_FALLBACK
        self.assertTrue(all(v is None or 1 <= v <= 87600
                            for row in REMINDER_DEFAULTS.values() for v in row))
        self.assertTrue(all(1 <= v <= 87600 for v in REMINDER_BASIS_FALLBACK))


if __name__=='__main__':
    unittest.main()
