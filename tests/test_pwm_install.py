"""Pinmux, user overlay, conflicting GPIO and per-channel access tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from tools.pwm_install import PINS, render_boot, mapping


class PWMInstallTests(unittest.TestCase):
    def test_installs_single_pin_overlay_and_audio_disable(self):
        for gpio, (channel, func) in PINS.items():
            out = render_boot('[all]\ndtparam=audio=on\n', gpio)
            self.assertIn('dtoverlay=pwm,pin=%d,func=%d' % (gpio, func), out)
            self.assertTrue(out.rstrip().endswith('# END PETREL HARDWARE PWM'))
            self.assertIn('dtparam=audio=off', out)
            self.assertEqual(render_boot(out, gpio), out)

    def test_preserves_compatible_external_dual_channel_overlay(self):
        src = ('[all]\ndtoverlay=pwm-2chan,pin=18,func=2,pin2=19,func2=2\n'
               'custom_setting=value\n')
        out = render_boot(src, 19)
        self.assertEqual(out.count('dtoverlay=pwm-2chan'), 1)
        self.assertIn('custom_setting=value', out)
        self.assertEqual(render_boot(out, 19), out)
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            render_boot(src, 13)

    def test_rejects_unmanaged_conflicts(self):
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            render_boot('dtoverlay=pwm,pin=12,func=4\n', 19)
        with self.assertRaisesRegex(ValueError, 'Multiple user'):
            render_boot('dtoverlay=pwm,pin=12,func=4\ndtoverlay=pwm-2chan\n', 12)

    def test_pwm1_channel_mapping(self):
        self.assertEqual(mapping('dtoverlay=pwm,pin=19,func=2'), {1: (19, 2)})
        self.assertEqual(mapping('dtoverlay=pwm-2chan,pin=12,func=4,pin2=19,func2=2'),
                         {0: (12, 4), 1: (19, 2)})


if __name__ == '__main__':
    unittest.main()
