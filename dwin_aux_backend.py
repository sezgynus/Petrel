"""Bounded adapter between the kernel TTY and DWIN broker.

Only one TX record is in flight. Completions wait a conservative serialization
interval because DWIN's transmit command has no physical TX-complete reply.
"""
import logging
import os
import struct
import time

from dwin_protocol import HEADER, TAIL, aux_baud_divisor

LOG = logging.getLogger(__name__)
RECORD = struct.Struct('<BIH')
LIMIT = 65536


def record(op, epoch, data=b''):
    return RECORD.pack(op, epoch, len(data)) + data


def decode(data):
    if len(data) < RECORD.size:
        raise ValueError('Short kernel UART record')
    op, epoch, length = RECORD.unpack_from(data)
    if length > 248 or len(data) != RECORD.size + length:
        raise ValueError('Invalid kernel UART record length')
    return op, epoch, data[RECORD.size:]


class AuxBackend:
    def __init__(self, path='/dev/dwin-uart-backend'):
        self.path = path
        self.fd = None
        self.watching = False
        self.tty_ready = False
        self.baud = 115200
        self.rx = bytearray()
        self.completion = None
        self.configuring = False
        self.reconnect_at = 0

    def _watch(self, enabled):
        if self.fd is None or self.watching == enabled:
            return
        if enabled:
            self.selector.register(self.fd, 1, 'backend')
        else:
            self.selector.unregister(self.fd)
        self.watching = enabled

    def _write(self, data):
        count = os.write(self.fd, data)
        if count != len(data):
            raise OSError('Partial kernel UART control write')

    def _configure(self, broker, requested):
        divisor, actual = aux_baud_divisor(requested)
        self.baud = round(actual)
        self.configuring = True
        self._watch(False)
        def complete():
            self.configuring = False
            self._write(record(4, 0, b'\x01'))
            self.tty_ready = True
            self._watch(True)
        broker.aux_tx.append(HEADER + b'\x38' + struct.pack('>H', divisor) + TAIL,
                             complete)
        broker._uart_events()

    def connected(self):
        # Initial configuration is queued by poll after the next handshake.
        self.configuring = False
        self.needs_configuration = True
        self.tty_ready = False

    def disconnected(self):
        self.close()
        self.rx.clear()
        self.completion = None
        self.configuring = False
        self.needs_configuration = True

    def receive(self, data):
        if len(self.rx) + len(data) > LIMIT:
            raise BufferError('Auxiliary RX overflow; disconnecting the TTY')
        self.rx.extend(data)

    def poll(self, broker):
        now = time.monotonic()
        if self.fd is None:
            if now < self.reconnect_at:
                return
            try:
                self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
                self.selector = broker.selector
                self._watch(True)
                self.needs_configuration = True
            except OSError:
                self.reconnect_at = now + 1
                return
        try:
            if self.completion is not None:
                deadline, epoch, count = self.completion
                if now < deadline:
                    return
                self._write(record(3, epoch, struct.pack('<I', count)))
                self.completion = None
                self._watch(True)
            # Drain received bytes with short-write/backpressure support.
            if self.rx and self.tty_ready:
                data = bytes(self.rx[:248])
                try:
                    count = os.write(self.fd, record(1, 0, data))
                    if not RECORD.size < count <= RECORD.size + len(data):
                        raise OSError('Invalid kernel UART RX acceptance')
                    del self.rx[:count - RECORD.size]
                except BlockingIOError:
                    pass
            if self.configuring:
                return
            try:
                data = os.read(self.fd, RECORD.size + 248)
            except BlockingIOError:
                data = None
            if data is not None:
                op, epoch, payload = decode(data)
                if op == 2 and len(payload) == 4:
                    self.baud = struct.unpack('<I', payload)[0]
                    if broker.online:
                        self._configure(broker, self.baud)
                        self.needs_configuration = False
                elif op == 1 and payload and broker.online:
                    from dwin_broker import aux_frames
                    # All chunks from this record complete before the next record.
                    frames = list(aux_frames(payload))
                    self.completion = (float('inf'), epoch, len(payload))
                    self._watch(False)
                    for index, frame in enumerate(frames):
                        def complete(frame=frame, last=index == len(frames) - 1):
                            # Physical host UART plus downstream serialization.
                            wait = (len(frame) + broker.uart.out_waiting) * 10 / 115200 + (len(frame) - 6) * 10 / self.baud
                            deadline = time.monotonic() + wait
                            broker.aux_ready_at = deadline
                            if last:
                                self.completion = (deadline, epoch, len(payload))
                        broker.aux_tx.append(frame, complete)
                    broker._uart_events()
                else:
                    raise ValueError('Unexpected kernel UART command')
            if broker.online and self.needs_configuration and not self.configuring:
                self._configure(broker, self.baud)
                self.needs_configuration = False
        except (OSError, ValueError, BufferError):
            LOG.exception('Auxiliary kernel transport failed')
            # In-flight records cannot be replayed safely after a backend fault.
            broker._disconnect()

    def close(self):
        if self.fd is not None:
            self._watch(False)
            os.close(self.fd)
            self.tty_ready = False
            self.fd = None
