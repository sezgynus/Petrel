"""Direct Raspberry Pi BCM283x hardware-PWM buzzer output.

Requires a boot PWM overlay and a service pre-start export/permission grant.
Never toggles a GPIO in software and never issues Klipper commands.
"""
import os
from pathlib import Path

# (BCM PWM channel, pinmux function used by the DT overlay).
PWM_PINS = {12: (0, 4), 13: (1, 4), 18: (0, 2), 19: (1, 2)}


def selected_gpio():
    if os.environ.get('PETREL_BUZZER_DISABLED') == '1':
        raise OSError('Hardware buzzer disabled until GPIOs are configured')
    value = int(os.environ.get('PETREL_BUZZER_GPIO', '19'))
    if value not in PWM_PINS:
        raise ValueError('Buzzer GPIO must be 12, 13, 18 or 19')
    return value


def find_chip(root=Path('/sys/class/pwm')):
    # A Pi Zero 2 W has a single BCM2835 PWM peripheral; never select some
    # unrelated pwmchip when another PWM provider happens to enumerate first.
    candidates = []
    for chip in sorted(root.glob('pwmchip*')):
        try:
            if int((chip / 'npwm').read_text()) >= 2:
                candidates.append(chip)
        except (OSError, ValueError):
            continue
    bcm = [path for path in candidates if ('3f20c000.pwm' in str(path.resolve())
                                          or 'fe20c000.pwm' in str(path.resolve()))]
    if len(bcm) == 1:
        return bcm[0]
    if len(candidates) == 1:
        return candidates[0]
    raise OSError('BCM2835 hardware PWM sysfs device not uniquely available')


class HardwarePWM:
    def __init__(self, gpio=None, root=Path('/sys/class/pwm')):
        gpio = selected_gpio() if gpio is None else gpio
        if gpio not in PWM_PINS:
            raise ValueError('Invalid hardware PWM GPIO')
        self.gpio = gpio
        self.channel = PWM_PINS[gpio][0]
        self.chip = find_chip(root)
        self.path = self.chip / ('pwm' + str(self.channel))
        if not self.path.is_dir():
            raise OSError('Hardware PWM not exported by Petrel service pre-start')

    def _write(self, name, value):
        (self.path / name).write_text(str(value))

    def tone(self, frequency, volume):
        if not 0 <= volume <= 100:
            raise ValueError('Invalid volume')
        # UI volume 100% corresponds to 50% *electrical* duty.
        self.set_pwm(frequency, volume / 200.)

    def set_pwm(self, frequency, duty):
        """Absolute PWM duty (0..1), as expected by Klipper SET_PIN."""
        if not 1 <= frequency <= 20000 or not 0 <= duty <= 1:
            raise ValueError('Invalid hardware PWM frequency/duty')
        if duty == 0:
            self.off()
            return
        period = round(1_000_000_000 / frequency)
        duty_ns = round(period * duty)
        # Zero duty before changing period; the kernel rejects duty > period.
        self._write('enable', 0)
        self._write('duty_cycle', 0)
        self._write('period', period)
        self._write('duty_cycle', duty_ns)
        self._write('enable', 1)

    def off(self):
        self._write('enable', 0)
        self._write('duty_cycle', 0)

    def close(self):
        self.off()
