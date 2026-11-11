"""Nonblocking panel handshake; keep one UART open while waiting for power."""
import time
import serial
from petrel.hardware.dwin.transport import open_display_serial


class PanelProbe:
    REQUEST = bytes.fromhex('AA 00 CC 33 C3 3C')
    RESPONSE = bytes.fromhex('AA 00 4F 4B CC 33 C3 3C')

    def __init__(self, port):
        self.serial = open_display_serial(port, serial.Serial, baudrate=115200, timeout=0, write_timeout=.05)
        self.received = bytearray()
        self.next_send = 0
        self.fast_until = 0
        # A DACAI panel keeps a raised host baud (0x38) until it loses power:
        # after a Petrel restart it may answer at either speed.
        from petrel.hardware.dwin import dacai
        baud = dacai.configured_baud() if dacai.enabled() else dacai.DEFAULT_BAUD
        self.alt_baud = baud if baud != dacai.DEFAULT_BAUD and isinstance(self.serial, serial.Serial) else 0

    def accelerate(self):
        self.fast_until = time.monotonic() + 10
        self.next_send = 0

    def poll(self):
        waiting = self.serial.in_waiting
        if waiting:
            self.received.extend(self.serial.read(min(waiting, 4096)))
            if self.RESPONSE in self.received:
                port, self.serial = self.serial, None
                return port
            self.received = self.received[-7:]
        now = time.monotonic()
        if now >= self.next_send:
            if self.alt_baud:
                self.serial.baudrate = self.alt_baud if self.serial.baudrate == 115200 else 115200
                self.received.clear()
            if self.serial.write(self.REQUEST) != len(self.REQUEST):
                raise OSError('Incomplete panel handshake write')
            self.next_send = now + (.15 if now < self.fast_until else 5)
        return None

    def close(self):
        if self.serial is not None:
            self.serial.close()
            self.serial = None
