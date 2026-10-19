"""Persistent buzzer preferences and a bounded, nonblocking PWM sound worker."""
from dataclasses import dataclass, replace
from threading import Condition, Thread
import math
import re
import struct
import time
import zlib

ADDRESS = 0x0400
RECORD_SIZE = 128
NAME = re.compile(r'[A-Za-z0-9_.:-]{1,96}')
TONES = ('Off', 'Tick', 'Short beep', 'Low', 'High', 'Double')
PATTERNS = ((), ((1800, .015),), ((1400, .055),), ((700, .055),),
            ((2400, .04),), ((1600, .035), (0, .035), (2000, .035)))

@dataclass(frozen=True)
class Settings:
    output: str = ''
    volume: int = 50
    click: int = 2
    encoder: int = 1

    def validate(self):
        if (self.output and not NAME.fullmatch(self.output) or
                not isinstance(self.volume, int) or not 0 <= self.volume <= 100 or
                not isinstance(self.click, int) or self.click not in range(len(TONES)) or
                not isinstance(self.encoder, int) or self.encoder not in range(len(TONES))):
            raise ValueError('Invalid buzzer settings')
        return self

    def encode(self):
        self.validate()
        body = struct.pack('>8sBBB', b'PETBZR01', self.volume, self.click, self.encoder)
        body += self.output.encode('ascii') + b'\0'
        body = body.ljust(RECORD_SIZE - 4, b'\0')
        return body + struct.pack('>I', zlib.crc32(body))

    @classmethod
    def decode(cls, raw):
        if len(raw) != RECORD_SIZE or raw[:8] not in (b'PETBZR01', b'KDWBZR01'):
            return None
        if zlib.crc32(raw[:-4]) != int.from_bytes(raw[-4:], 'big'):
            return None
        try:
            return cls(raw[11:-4].split(b'\0', 1)[0].decode('ascii'), *raw[8:11]).validate()
        except (ValueError, UnicodeError):
            return None


def outputs(settings, objects):
    # Effective config keys are lowercase; SET_PIN names retain object-name case.
    configured = {key.casefold() for key in settings if key.startswith('pwm_cycle_time ')}
    return tuple(sorted((key[15:] for key in objects
                         if key.startswith('pwm_cycle_time ') and NAME.fullmatch(key[15:])
                         and key.casefold() in configured),
                        key=str.casefold))


def resolve_output(name, names):
    if name in names:
        return name
    matches = [value for value in names if value.casefold() == name.casefold()]
    return matches[0] if len(matches) == 1 else ''


def available(snapshot):
    return outputs(snapshot.get('settings', {}), snapshot.get('objects', ()))


class Player:
    def __init__(self, subscription):
        self.subscription = subscription
        self.condition = Condition()
        self.pending = None
        self.busy = False
        self.stopped = False
        self.generation = 0
        self.thread = Thread(target=self._run, name='petrel-buzzer', daemon=True)
        self.thread.start()

    def _snapshot(self):
        reader = getattr(type(self.subscription), 'buzzer_snapshot', None)
        return (self.subscription.buzzer_snapshot() if callable(reader)
                else self.subscription.snapshot())

    def play(self, settings, kind):
        settings.validate()
        tone = settings.click if kind == 'press' else settings.encoder
        if not settings.output or not settings.volume or not tone:
            return False
        with self.condition:
            if self.stopped or self.busy or self.pending is not None:
                return False
        snapshot = self._snapshot()
        name = resolve_output(settings.output, available(snapshot))
        if snapshot['state'] != 'ready' or not name:
            return False
        settings = replace(settings, output=name)
        with self.condition:
            if self.stopped or self.busy or self.pending is not None:
                return False
            self.pending = (settings, tone, snapshot['epoch'], self.generation, time.monotonic())
            self.condition.notify()
        return True

    def cancel(self):
        with self.condition:
            self.pending = None
            self.generation += 1
            self.condition.notify_all()

    def _send(self, script, epoch, guard=None):
        def ready():
            snapshot = self._snapshot()
            return snapshot['state'] == 'ready' and snapshot['epoch'] == epoch and (guard is None or guard())
        self.subscription.notify_immediate('printer.gcode.script', {'script': script}, guard=ready).result(timeout=1)

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.stopped or self.pending is not None)
                if self.stopped:
                    return
                settings, tone, epoch, generation, queued = self.pending
                self.pending = None
                self.busy = True
            active = False
            try:
                snapshot = self._snapshot()
                key = ('pwm_cycle_time ' + settings.output).casefold()
                config = next((value for section, value in snapshot.get('settings', {}).items()
                               if section.casefold() == key), {})
                scale = float(config.get('scale') or 1)
                if not math.isfinite(scale) or scale <= 0:
                    continue
                for frequency, duration in PATTERNS[tone]:
                    with self.condition:
                        if self.stopped or generation != self.generation:
                            break
                    def valid():
                        current = self._snapshot()
                        return (not self.stopped and generation == self.generation and
                                time.monotonic() - queued < .5 and
                                settings.output in available(current))
                    command = 'SET_PIN PIN={} VALUE={:g}'.format(settings.output, settings.volume / 200 * scale if frequency else 0)
                    if frequency:
                        command += ' CYCLE_TIME={:.8f}'.format(1 / frequency)
                    active = bool(frequency)
                    self._send(command, epoch, valid)
                    with self.condition:
                        self.condition.wait_for(lambda: self.stopped or generation != self.generation, timeout=duration)
                    self._send('SET_PIN PIN={} VALUE=0'.format(settings.output), epoch,
                               lambda: settings.output in available(self._snapshot()))
                    active = False
            except Exception:
                # Sounds are optional and must not interrupt UI/printer actions.
                pass
            finally:
                try:
                    if active:
                        self._send('SET_PIN PIN={} VALUE=0'.format(settings.output), epoch,
                                   lambda: settings.output in available(self._snapshot()))
                except Exception:
                    pass
                with self.condition:
                    self.busy = False

    def close(self):
        with self.condition:
            self.stopped = True
            self.pending = None
            self.generation += 1
            self.condition.notify_all()
        self.thread.join(timeout=2)
