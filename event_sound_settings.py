"""Stable per-event disabled bits in a separate 16-byte DWIN Flash record."""
from dataclasses import dataclass, replace
import struct
import zlib

# Outside both modern and legacy 0x0400..0x047F buzzer records.
ADDRESS = 0x0480
RECORD_SIZE = 16
MAGIC = b'PETEVT01'
# Append only: bit identities must survive reordering, localization and upgrades.
EVENTS = (
    ('BOOT', 'Startup'),
    ('SHUTDOWN', 'Power off'),
    ('PRINT_DONE', 'Print completed'),
    ('PAUSE', 'Print paused'),
    ('RESUME', 'Print resumed'),
    ('ERROR', 'Printer error'),
    ('HEATING_DONE', 'Heating completed'),
    ('COOLING_DONE', 'Cooling completed'),
    ('HOMING', 'Homing'),
    ('PROBE_SUCCESS', 'Probe succeeded'),
    ('PROBE_FAIL', 'Probe failed'),
    ('LAYER_CHANGE', 'Layer changed'),
    ('FILAMENT_OUT', 'Filament runout'),
    ('NFC_TAG_READ', 'RFID tag read'),
    ('NFC_SPOOL_MATCH', 'Spool tag matched'),
    ('NFC_SHARE_DONE', 'NFC share completed'),
    ('EMERGENCY', 'Emergency card alarm'),
    ('POWER_HOLD', 'Power button hold'),
)
CUE_EVENTS = {name: 'POWER_HOLD' for name in (
    'POWER_HOLD_START', 'POWER_HOLD_STEP', 'POWER_HOLD_READY', 'POWER_HOLD_CANCEL')}
BITS = {name: 1 << index for index, (name, _) in enumerate(EVENTS)}


@dataclass(frozen=True)
class EventSounds:
    # Zero disables nothing. Future appended events default to enabled too.
    disabled: int = 0

    def validate(self):
        if type(self.disabled) is not int or not 0 <= self.disabled <= 0xFFFFFFFF:
            raise ValueError('Invalid event sound mask')
        return self

    def enabled(self, name):
        return not bool(self.disabled & BITS.get(CUE_EVENTS.get(name, name), 0))

    def toggled(self, name):
        return replace(self, disabled=self.disabled ^ BITS[name]).validate()

    def encode(self):
        self.validate()
        payload = struct.pack('>8sI', MAGIC, self.disabled)
        return payload + struct.pack('>I', zlib.crc32(payload))

    @classmethod
    def decode(cls, raw):
        if not isinstance(raw, (bytes, bytearray)) or len(raw) != RECORD_SIZE:
            return None
        magic, disabled, crc = struct.unpack('>8sII', raw)
        if magic != MAGIC or zlib.crc32(raw[:12]) != crc:
            return None
        return cls(disabled)
