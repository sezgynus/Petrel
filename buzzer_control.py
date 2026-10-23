"""Persistent buzzer preferences and bounded nonblocking *hardware* PWM worker."""
from dataclasses import dataclass
from threading import Condition, Thread
import logging
import struct
import time
import zlib

from buzzer_pwm import HardwarePWM

ADDRESS = 0x0400
RECORD_SIZE = 128
TONES = ('Off', 'Tick', 'Short beep', 'Low', 'High', 'Double')
PATTERNS = ((), ((1800, .015),), ((1400, .055),), ((700, .055),),
            ((2400, .04),), ((1600, .035), (0, .035), (2000, .035)))


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
    def __init__(self, subscription=None, driver_factory=HardwarePWM):
        # 'subscription' is accepted only so older callers do not break.
        # Hardware sound is completely independent of Klipper/Moonraker.
        self.driver_factory = driver_factory
        self.condition = Condition()
        self.pending = None
        self.busy = False
        self.stopped = False
        self.generation = 0
        self.last_error = None
        self.thread = Thread(target=self._run, name='petrel-buzzer', daemon=True)
        self.thread.start()

    def play(self, settings, kind, priority=False):
        settings.validate()
        tone = settings.click if kind == 'press' else settings.encoder
        if not settings.enabled or settings.volume == 0 or tone == 0:
            return False
        with self.condition:
            if self.stopped or (not priority and (self.busy or self.pending is not None)):
                return False
            if priority:
                self.generation += 1
            self.pending = (settings, tone, self.generation)
            self.condition.notify_all()
            return True

    def cancel(self):
        with self.condition:
            self.pending = None
            self.generation += 1
            self.condition.notify_all()

    def _run(self):
        driver = None
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.stopped or self.pending is not None)
                    if self.stopped:
                        return
                    settings, tone, generation = self.pending
                    self.pending = None
                    self.busy = True
                try:
                    if driver is None:
                        driver = self.driver_factory()
                    self.last_error = None
                    for frequency, duration in PATTERNS[tone]:
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
                    # A missing overlay/permission must not block printer UI.
                    message = str(error)
                    if message != self.last_error:
                        logging.warning('Hardware buzzer unavailable: %s', message)
                        self.last_error = message
                    driver = None
                finally:
                    if driver is not None:
                        try:
                            driver.off()
                        except OSError:
                            driver = None
                    with self.condition:
                        self.busy = False
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
            self.generation += 1
            self.condition.notify_all()
        self.thread.join(timeout=2)
