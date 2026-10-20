"""Event-only capture regression: original firmware callbacks stay authoritative."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
from test_axis_travel_extra import extra_module


class Switch:
    def __init__(self):
        self.calls = []
    def button_callback(self, when, value):
        self.calls.append((when, value))
        return 'original-result'


class Debouncer:
    def __init__(self, target, initial=False):
        self.button_action = target.button_callback
        self.logical_state = initial
    def button_handler(self, when, value):
        self.logical_state = value
        return self.button_action(when, value)


class Endstop:
    def __init__(self):
        self.hit = 1.5
        self.started = []
        self.waited = []
    def home_start(self, *args, triggered=True):
        self.started.append((args, triggered))
        return 'completion'
    def home_wait(self, when):
        self.waited.append(when)
        if isinstance(self.hit, Exception):
            raise self.hit
        return self.hit


def setup(extra_names=(), probe=None):
    target = Switch()
    debounce = Debouncer(target)
    group = NS(callbacks=[(1, 0, debounce.button_handler)], pin_list=['PA1'])
    # First group is absent from buttons.mcu_buttons, as happens above eight pins.
    later_group = NS(callbacks=[], pin_list=['PA2'])
    class Group:
        def __init__(self, group):
            self.callbacks, self.pin_list = group.callbacks, group.pin_list
        def build_config(self):
            pass
    first = Group(group)
    mcu = NS(_config_helper=NS(_config_callbacks=[first.build_config]))
    buttons = NS(mcu_buttons={'mcu': later_group}, adc_buttons={})
    endstop = Endstop()
    query = NS(endstops=[(endstop, 'stepper_x')])
    configfile = NS(get_status=lambda now: {'settings': {
        'stepper_x': {'endstop_pin': '^PA0'}}})
    objects = [('gcode_button arbitrary', target), ('mcu', mcu), ('buttons', buttons),
               ('query_endstops', query), ('configfile', configfile)]+list(extra_names)
    if probe is not None:
        objects.append(('probe', probe))
    printer = NS(lookup_objects=lambda: objects,
                 lookup_object=lambda name, default=None: dict(objects).get(name, default),
                 register_event_handler=Mock())
    module = extra_module()
    capture = module.SensorEvents(printer)
    capture.ready()
    return capture, target, debounce, endstop, printer


class SensorEventExtraTests(unittest.TestCase):
    def test_all_button_groups_are_observed_without_new_pin_registration_or_timer(self):
        capture, target, debounce, _, printer = setup()
        for when, value in enumerate((True, True, False, True, False)):
            result = debounce.button_handler(when, value)
            self.assertEqual(result, 'original-result')
        self.assertEqual(capture.counts['gcode_button arbitrary'], 2)
        self.assertEqual(len(target.calls), 5)
        self.assertEqual(capture.kinds['gcode_button arbitrary'], 'switch_activation')
        self.assertFalse(hasattr(printer, 'register_timer'))
        # READY can never attach a second counting wrapper.
        capture.ready()
        debounce.button_handler(10, True)
        self.assertEqual(capture.counts['gcode_button arbitrary'], 3)

    def test_initial_active_state_and_shutdown_do_not_fabricate_activations(self):
        capture, target, debounce, _, _ = setup()
        # A source without a known initial level is baselined.
        callback = capture._edge_callback(target.button_callback, 'gcode_button arbitrary', None)
        callback(0, True)
        callback(1, True)
        self.assertEqual(capture.counts['gcode_button arbitrary'], 0)
        callback(2, False)
        callback(3, True)
        self.assertEqual(capture.counts['gcode_button arbitrary'], 1)
        capture.stop()
        callback(4, False)
        callback(5, True)
        self.assertEqual(capture.counts['gcode_button arbitrary'], 1)
        self.assertEqual(len(target.calls), 6)

    def test_original_callback_return_and_exception_are_preserved(self):
        capture, _, _, _, _ = setup()
        original = Mock(side_effect=RuntimeError('original failure'))
        callback = capture._edge_callback(original, 'gcode_button arbitrary', False)
        with self.assertRaisesRegex(RuntimeError, 'original failure'):
            callback(1, True)
        original.assert_called_once_with(1, True)
        self.assertEqual(capture.counts['gcode_button arbitrary'], 0)

    def test_analog_debounced_button_uses_existing_callback(self):
        target = Switch()
        debounce = Debouncer(target)
        group = NS(buttons=[(.1, .2, debounce.button_handler)])
        buttons = NS(mcu_buttons={}, adc_buttons={'PA2': group})
        objects = [('gcode_button analog', target), ('buttons', buttons)]
        printer = NS(lookup_objects=lambda: objects, register_event_handler=Mock(),
                     lookup_object=lambda name, default=None: dict(objects).get(name, default))
        capture = extra_module().SensorEvents(printer)
        capture.ready()
        debounce.button_handler(1, True)
        self.assertEqual(capture.counts, {'gcode_button analog': 1})
        self.assertEqual(target.calls, [(1, True)])

    def test_motion_sensor_counts_rising_encoder_edges_not_presence_timer(self):
        class Encoder:
            def __init__(self): self.calls = []
            def encoder_event(self, t, value): self.calls.append((t, value))
        encoder = Encoder()
        group = NS(callbacks=[(1, 0, encoder.encoder_event)], pin_list=['PA0'])
        objects = [('filament_motion_sensor arbitrary', encoder),
                   ('buttons', NS(mcu_buttons={'mcu': group}, adc_buttons={}))]
        printer = NS(lookup_objects=lambda: objects, register_event_handler=Mock(),
                     lookup_object=lambda name, default=None: dict(objects).get(name, default))
        capture = extra_module().SensorEvents(printer)
        capture.ready()
        callback = group.callbacks[0][2]
        for t, value in enumerate((True, False, True, False, True)):
            callback(t, value)
        self.assertEqual(capture.counts['filament_motion_sensor arbitrary'], 2)
        self.assertEqual(capture.kinds['filament_motion_sensor arbitrary'], 'encoder_rising_edge')
        self.assertEqual(len(encoder.calls), 5)

    def test_positive_homing_hit_and_real_movement_count_once_and_restore_methods(self):
        capture, _, _, endstop, _ = setup()
        original_start, original_wait = endstop.home_start, endstop.home_wait
        hmove = NS(endstops=[(endstop, 'stepper_x')],
                   stepper_positions=[NS(endstop_name='stepper_x', start_pos=0, trig_pos=10)])
        capture.begin(hmove)
        self.assertEqual(endstop.home_start(1, 2, 3, 4), 'completion')
        self.assertEqual(endstop.home_wait(2), 1.5)
        capture.end(hmove)
        capture.end(hmove)
        self.assertEqual(capture.counts['endstop stepper_x'], 1)
        self.assertEqual(endstop.home_start, original_start)
        self.assertEqual(endstop.home_wait, original_wait)
        # A two-pass homing contains two distinct physical contacts.
        capture.begin(hmove)
        endstop.home_start(1, 2, 3, 4)
        endstop.home_wait(2)
        capture.end(hmove)
        self.assertEqual(capture.counts['endstop stepper_x'], 2)

    def test_timeout_release_no_movement_and_errors_never_count(self):
        for hit, triggered, moved in ((0., True, True), (float('nan'), True, True),
                                     (2., False, True), (2., True, False),
                                     (RuntimeError('timeout'), True, True)):
            with self.subTest(hit=hit, triggered=triggered, moved=moved):
                capture, _, _, endstop, _ = setup()
                endstop.hit = hit
                original = endstop.home_wait
                hmove = NS(endstops=[(endstop, 'stepper_x')],
                           stepper_positions=[NS(endstop_name='stepper_x', start_pos=0, trig_pos=int(moved))])
                capture.begin(hmove)
                endstop.home_start(1, 2, 3, 4, triggered=triggered)
                if isinstance(hit, Exception):
                    with self.assertRaises(RuntimeError): endstop.home_wait(2)
                    capture._clear_moves()
                else:
                    endstop.home_wait(2)
                    capture.end(hmove)
                self.assertEqual(capture.counts['endstop stepper_x'], 0)
                self.assertEqual(endstop.home_wait, original)

    def test_contact_probe_and_endstop_are_independent_and_no_new_queries(self):
        probe_endstop = Endstop()
        probe = NS(mcu_probe=NS(homing_helper=NS(mcu_probe=probe_endstop)))
        capture, _, _, endstop, _ = setup(probe=probe)
        hmove = NS(endstops=[(probe_endstop, 'probe')],
                   stepper_positions=[NS(endstop_name='probe', start_pos=0, trig_pos=5)])
        capture.begin(hmove)
        probe_endstop.home_start(1, 2, 3, 4)
        probe_endstop.home_wait(2)
        capture.end(hmove)
        self.assertEqual(capture.counts['probe'], 1)
        self.assertEqual(capture.counts['endstop stepper_x'], 0)
        self.assertEqual(probe_endstop.waited, [2])

    def test_capacity_and_overflow_disable_optional_counting_only(self):
        capture, target, debounce, _, _ = setup()
        for i in range(100):
            capture._add('gcode_button b%03d' % i, 'switch_activation')
        self.assertEqual(len(capture.counts), 64)
        capture.counts['gcode_button arbitrary'] = 2**53-1
        debounce.button_handler(1, True)
        self.assertEqual(capture.counts['gcode_button arbitrary'], 2**53-1)
        self.assertIn('gcode_button arbitrary', capture.status()['sensor_disabled'])
        self.assertEqual(target.calls, [(1, True)])
