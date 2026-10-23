import contextlib
import io
import os
import unittest
from unittest.mock import patch

import run


class ConfigTests(unittest.TestCase):
    def test_environment_defaults(self):
        values = dict(MOONRAKER_URL='http://printer:7125', PETREL_SERIAL_PORT='/dev/test',
                      PETREL_ENCODER_PINS='26 16', PETREL_BUTTON_PIN='13',
                      PETREL_REQUEST_TIMEOUT='2.5', PETREL_SETTINGS_FILE='/tmp/presets.json',
                      PETREL_POWER_DEVICE='Printer', PETREL_POWER_ON_HOLD_MS='1500')
        with patch.dict(os.environ, values, clear=True):
            args = run.parse_args([])
        self.assertEqual(args.encoder_pins, (26, 16))
        self.assertEqual(args.request_timeout, 2.5)
        self.assertEqual(args.serial_port, '/dev/test')
        self.assertEqual(args.settings_file, '/tmp/presets.json')
        self.assertEqual(args.moonraker_url, 'http://printer:7125')
        self.assertEqual(args.power_device, 'Printer')
        self.assertEqual(args.power_on_hold_ms, 1500)

    def test_cli_overrides_environment(self):
        with patch.dict(os.environ, {'PETREL_ENCODER_PINS': '26 19', 'PETREL_REQUEST_TIMEOUT': '2'}, clear=True):
            args = run.parse_args(['--encoder-pins', '21', '16', '--request-timeout', '3'])
        self.assertEqual(args.encoder_pins, (21, 16))
        self.assertEqual(args.request_timeout, 3)

    def test_invalid_configuration_exits_before_hardware_import(self):
        for values in (dict(PETREL_ENCODER_PINS='21'), dict(PETREL_ENCODER_PINS='13 19'),
                       dict(PETREL_BUZZER_GPIO='17'), dict(PETREL_BUZZER_GPIO='16'),
                       dict(PETREL_ENCODER_PINS='28 19'), dict(PETREL_REQUEST_TIMEOUT='nan'),
                       dict(PETREL_REQUEST_TIMEOUT='0'), dict(PETREL_BUTTON_PIN='invalid'),
                       dict(PETREL_POWER_ON_HOLD_MS='-1'), dict(PETREL_POWER_ON_HOLD_MS='invalid')):
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    run.parse_args([])
                self.assertEqual(error.exception.code, 2)


    def test_buzzer_pwm_defaults_and_conflict_validation(self):
        with patch.dict(os.environ, {}, clear=True):
            args = run.parse_args([])
        self.assertEqual(args.encoder_pins, (21, 16))
        self.assertEqual(args.buzzer_gpio, 19)
        with patch.dict(os.environ, {'PETREL_BUZZER_GPIO': '12'}, clear=True):
            self.assertEqual(run.parse_args([]).buzzer_gpio, 12)


class EmulatorConfigTests(unittest.TestCase):
    def test_emulator_defaults_off_and_cli_overrides_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(run.parse_args([]).emulator)
        with patch.dict(os.environ, {'PETREL_EMULATOR': '1'}, clear=True):
            self.assertTrue(run.parse_args([]).emulator)
            self.assertFalse(run.parse_args(['--no-emulator']).emulator)
        args = run.parse_args(['--emulator', '--emulator-font', '/tmp/font.hzk'])
        self.assertTrue(args.emulator)
        self.assertEqual(args.emulator_font, '/tmp/font.hzk')
