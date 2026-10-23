"""Persistent buzzer preferences and bounded nonblocking *hardware* PWM worker."""
from dataclasses import dataclass
from threading import Condition, Thread
import logging
import math
import struct
import time
import zlib

from buzzer_pwm import HardwarePWM

ADDRESS = 0x0400
RECORD_SIZE = 128
TONES = ('Off', 'Tick', 'Short beep', 'Low', 'High', 'Double')
PATTERNS = ((), ((1800, .015),), ((1400, .055),), ((700, .055),),
            ((2400, .04),), ((1600, .035), (0, .035), (2000, .035)))
# Three urgent two-tone sweeps and a distinct double high alert (~1.5 s).
# Never routed through Klipper: all steps run on the Pi PWM worker.
EMERGENCY_PATTERN = ((2200, .12), (1000, .12), (2200, .12),
                     (1000, .12), (2200, .12), (1000, .30),
                     (0, .09), (2600, .13), (0, .07), (2600, .28))


@dataclass(frozen=True)
class Settings:
    enabled: bool = True
    volume: int = 50
    click: int = 2
    encoder: int = 1

    def validate(self):
        if (type(self.enabled) is not bool or
                type(self.volume) is not int or not 0 <= self.volume <= 100 or
                type(self.click) is not int or self.click not in range(len(TONES)) or
                type(self.encoder) is not int or self.encoder not in range(len(TONES))):
            raise ValueError('Invalid buzzer settings')
        return self

    def encode(self):
        self.validate()
        body = struct.pack('>8sBBBB', b'PETBZR02', self.volume, self.click,
                           self.encoder, int(self.enabled))
        body = body.ljust(RECORD_SIZE - 4, b'\0')
        return body + struct.pack('>I', zlib.crc32(body))

    @classmethod
    def decode(cls, raw):
        if len(raw) != RECORD_SIZE or raw[:8] not in (b'PETBZR02', b'PETBZR01', b'KDWBZR01'):
            return None
        if zlib.crc32(raw[:-4]) != int.from_bytes(raw[-4:], 'big'):
            return None
        try:
            if raw[:8] == b'PETBZR02':
                if raw[11] not in (0, 1):
                    return None
                return cls(bool(raw[11]), *raw[8:11]).validate()
            # Legacy output selection was saved in DWIN Flash. Import only its
            # enabled/disabled state; never retain or send the Klipper name.
            return cls(bool(raw[11:-4].split(b'\0', 1)[0]), *raw[8:11]).validate()
        except (ValueError, TypeError):
            return None


class Player:
    """Single owning thread for PWM: emergency > UI tones > Klipper SET_PIN.

    External SET_PIN levels persist until changed or a 30-second safety cutoff.
    A UI click briefly overlays that state; emergency clears it permanently.
    No listener or UI thread ever writes sysfs directly.
    """
    EXTERNAL_MAX_SECONDS = 30.

    def __init__(self, subscription=None, driver_factory=HardwarePWM):
        self.driver_factory = driver_factory
        self.condition = Condition()
        self.pending = None
        self.busy = False
        self.stopped = False
        self.generation = 0
        self.last_error = None
        self.external = None
        self.external_expires = 0.
        self.external_dirty = False
        self.emergency_active = False
        self.emergency_pending = False
        self.thread = Thread(target=self._run, name='petrel-buzzer', daemon=True)
        self.thread.start()

    def play(self, settings, kind, priority=False):
        settings.validate()
        tone = settings.click if kind == 'press' else settings.encoder
        if not settings.enabled or settings.volume == 0 or tone == 0:
            return False
        with self.condition:
            if (self.stopped or self.emergency_active or self.emergency_pending
                    or (not priority and (self.busy or self.pending is not None))):
                return False
            if priority:
                self.generation += 1
            self.pending = (settings, tone, self.generation)
            self.condition.notify_all()
            return True

    def set_external(self, value, cycle_time):
        """Queue an absolute duty fraction from Klipper, independent of UI volume."""
        if (not math.isfinite(value) or not 0. <= value <= 1.
                or not math.isfinite(cycle_time) or not .00005 <= cycle_time <= 1.):
            return False
        with self.condition:
            if self.stopped or self.emergency_active or self.emergency_pending:
                return False
            self.external = (value, cycle_time) if value else None
            self.external_expires = time.monotonic() + self.EXTERNAL_MAX_SECONDS
            self.external_dirty = True
            self.condition.notify_all()
            return True

    def mute_external(self):
        """Clear Klipper's latched duty when the master buzzer is disabled."""
        with self.condition:
            self.external = None
            self.external_dirty = True
            self.condition.notify_all()

    def play_emergency(self):
        """Preempt all sounds; Klipper events cannot interrupt the alarm."""
        with self.condition:
            if self.stopped:
                return False
            self.generation += 1
            self.external = None
            self.external_dirty = False
            self.emergency_pending = True
            self.pending = (Settings(enabled=True, volume=100), 'emergency',
                            self.generation)
            self.condition.notify_all()
            return True

    def cancel(self):
        with self.condition:
            if self.emergency_active or self.emergency_pending:
                return  # The emergency alert cannot be cancelled by UI preferences.
            self.pending = None
            self.generation += 1
            self.condition.notify_all()

    def _run(self):
        driver = None
        try:
            while True:
                with self.condition:
                    remaining = (max(0., self.external_expires - time.monotonic())
                                 if self.external is not None else None)
                    self.condition.wait_for(
                        lambda: self.stopped or self.pending is not None or self.external_dirty,
                        timeout=remaining)
                    if self.stopped:
                        return
                    if self.external is not None and time.monotonic() >= self.external_expires:
                        self.external = None
                        self.external_dirty = True
                    if self.pending is not None:
                        settings, tone, generation = self.pending
                        self.pending = None
                        self.busy = True
                        self.emergency_active = tone == 'emergency'
                        if self.emergency_active:
                            self.emergency_pending = False
                        external_state = None
                    else:
                        settings = tone = generation = None
                        external_state = self.external
                        self.external_dirty = False
                try:
                    if driver is None:
                        driver = self.driver_factory()
                    self.last_error = None
                    if tone is None:
                        if external_state is None:
                            driver.off()
                        else:
                            value, cycle_time = external_state
                            driver.set_pwm(1. / cycle_time, value)
                    else:
                        pattern = EMERGENCY_PATTERN if tone == 'emergency' else PATTERNS[tone]
                        for frequency, duration in pattern:
                            with self.condition:
                                if self.stopped or generation != self.generation:
                                    break
                            if frequency:
                                driver.tone(frequency, settings.volume)
                            else:
                                driver.off()
                            with self.condition:
                                self.condition.wait_for(
                                    lambda: self.stopped or generation != self.generation,
                                    timeout=duration)
                            driver.off()
                except (OSError, ValueError) as error:
                    message = str(error)
                    if message != self.last_error:
                        logging.warning('Hardware buzzer unavailable: %s', message)
                        self.last_error = message
                    driver = None
                finally:
                    if tone is not None:
                        if driver is not None:
                            try:
                                driver.off()
                            except OSError:
                                driver = None
                        with self.condition:
                            self.busy = False
                            if tone == 'emergency':
                                self.emergency_active = False
                                self.external = None
                                self.external_dirty = False
                            elif self.external is not None:
                                self.external_dirty = True
                            self.condition.notify_all()
        finally:
            if driver is not None:
                try:
                    driver.close()
                except OSError:
                    pass

    def close(self):
        with self.condition:
            self.stopped = True
            self.pending = None
            self.external = None
            self.generation += 1
            self.condition.notify_all()
        self.thread.join(timeout=2)
