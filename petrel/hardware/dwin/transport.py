"""Optional local packet transport; direct UART remains the default."""
import os
import select
import socket
import time


class BrokerSerial:
    """Small pySerial-compatible surface used by the panel driver/probe only."""
    def __init__(self, path, timeout=0.05, write_timeout=1):
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._buffer = bytearray()
        self._drain_acks = 0
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            self._socket.settimeout(max(1, write_timeout))
            self._socket.connect(path)
            # Accept/reject is explicit: a second UI must not steal an owner's RX.
            if self._socket.recv(16) != b'DWIN1':
                raise OSError('DWIN broker rejected display connection')
            self._socket.setblocking(False)
        except BaseException:
            self._socket.close()
            raise

    def _receive(self):
        try:
            data = self._socket.recv(512)
        except BlockingIOError:
            return
        if not data:
            raise OSError('DWIN broker disconnected')
        if data == b'\x00':
            # Broker drain reply is transport control, never a DWIN packet.
            self._drain_acks += 1
        else:
            self._buffer.extend(data)

    @property
    def in_waiting(self):
        if not self._buffer:
            self._receive()
        return len(self._buffer)

    def read(self, size):
        if not self._buffer:
            ready, _, _ = select.select([self._socket], [], [], self.timeout)
            if ready:
                self._receive()
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def write(self, data):
        _, ready, _ = select.select([], [self._socket], [], self.write_timeout)
        if not ready:
            raise TimeoutError('DWIN broker write timeout')
        return self._socket.send(data)

    def flush(self):
        """Wait for the broker to drain preceding display packets to UART.

        A socket send only enqueues the bytes at the broker. Unlike a no-op,
        this barrier preserves pySerial's ordering guarantee before panel
        Picture Flash is committed. It is used only during asset transfers.
        """
        if self.write(b'\x00') != 1:
            raise OSError('Incomplete DWIN UART drain request')
        deadline = time.monotonic() + 20.0
        while not self._drain_acks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise TimeoutError('DWIN broker UART drain acknowledgement timed out')
            readable, _, _ = select.select([self._socket], [], [], remaining)
            if readable:
                self._receive()
        self._drain_acks -= 1

    def close(self):
        self._socket.close()


def open_display_serial(port, factory, **options):
    path = os.environ.get('PETREL_DWIN_SOCKET', '')
    if path:
        options.pop('baudrate', None)
        return BrokerSerial(path, **options)
    return factory(port, **options)
