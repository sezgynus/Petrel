import unittest
from unittest.mock import Mock

from test_capabilities import snapshot, printer, display


def data():
    result = snapshot()
    result['status']['toolhead'].update(max_velocity=150, max_accel=3000,
                                       square_corner_velocity=5, minimum_cruise_ratio=.5)
    return result


class MotionTests(unittest.TestCase):
    def test_four_live_parameters_and_correct_commands(self):
        result = printer(data())
        settings = result.motion_settings()
        self.assertEqual(len(settings), 4)
        for field, argument, _, _, value in settings:
            result.sendGCode.reset_mock()
            returned = result.set_motion_limit(field, value)
            result.sendGCode.assert_called_once_with(
                'SET_VELOCITY_LIMIT {}={:g}'.format(argument, value))
            self.assertIs(returned, result.sendGCode.return_value)
        self.assertEqual(result.state.status['toolhead']['max_accel'], 3000)

    def test_klipper_numeric_domains_are_enforced(self):
        result = printer(data())
        for field, value in (('max_velocity', 0), ('max_accel', -1),
                              ('square_corner_velocity', -.1), ('minimum_cruise_ratio', 1),
                              ('minimum_cruise_ratio', -.01), ('max_velocity', float('nan')),
                              ('max_accel', float('inf')), ('max_velocity\nG28', 10)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                result.set_motion_limit(field, value)
        result.sendGCode.assert_not_called()
        result.set_motion_limit('square_corner_velocity', 0)
        result.set_motion_limit('minimum_cruise_ratio', 0)

    def test_missing_or_invalid_parameters_are_not_invented(self):
        source = data()
        del source['status']['toolhead']['minimum_cruise_ratio']
        source['status']['toolhead']['max_accel'] = float('nan')
        result = printer(source)
        self.assertEqual([item[0] for item in result.motion_settings()],
                         ['max_velocity', 'square_corner_velocity'])
        with self.assertRaises(ValueError):
            result.set_motion_limit('minimum_cruise_ratio', .5)

    def test_ui_edits_only_target_then_submits_on_confirm(self):
        result = display(data())
        result.checkkey = result.Motion
        result.select_motion.set(1)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_Motion()
        self.assertEqual(result.checkkey, result.MotionValue)
        self.assertEqual(result._motion_target, 150)
        result.get_encoder_state.return_value = result.ENCODER_DIFF_CW
        result.HMI_MotionValue()
        self.assertEqual(result._motion_target, 151)
        self.assertEqual(result.pd.state.status['toolhead']['max_velocity'], 150)
        result.pd.sendGCode.assert_not_called()
        result.get_encoder_state.return_value = result.ENCODER_DIFF_ENTER
        result.HMI_MotionValue()
        result.pd.sendGCode.assert_called_once_with('SET_VELOCITY_LIMIT VELOCITY=151')
        self.assertEqual(result.checkkey, result.Motion)

    def test_cruise_ratio_encoder_never_reaches_one(self):
        source = data()
        source['status']['toolhead']['minimum_cruise_ratio'] = .99
        result = display(source)
        result.checkkey = result.Motion
        result.select_motion.set(4)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_Motion()
        result.get_encoder_state.return_value = result.ENCODER_DIFF_CW
        result.HMI_MotionValue()
        self.assertEqual(result._motion_target, .99)
        result.get_encoder_state.return_value = result.ENCODER_DIFF_ENTER
        result.HMI_MotionValue()
        result.pd.sendGCode.assert_called_once_with('SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0.99')

    def test_menu_values_follow_status_and_labels_are_klipper_specific(self):
        result = display(data())
        result.checkkey = result.Motion
        result.Draw_Menu_Line = Mock()
        result.Draw_Motion_Menu()
        labels = [call.args[-1] for call in result.Draw_Menu_Line.call_args_list if isinstance(call.args[-1], str)]
        self.assertEqual(labels, ['Velocity mm/s', 'Accel mm/s2', 'SCV mm/s', 'Cruise ratio'])
        source = data()
        source['status']['toolhead']['max_accel'] = 2000
        result.pd.subscription.snapshot.return_value = source
        result.pd.update_variable()
        self.assertEqual(result.pd.motion_settings()[1][-1], 2000)
        result.pd.sendGCode.assert_not_called()
