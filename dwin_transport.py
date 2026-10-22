"""Optional local packet transport; direct UART remains the default."""
import os
import select
import socket


class BrokerSerial:
    """Small pySerial-compatible surface used by the panel driver/probe only."""
    def __init__(self, path, timeout=0.05, write_timeout=1):
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._buffer = bytearray()
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

    def close(self):
        self._socket.close()


def open_display_serial(port, factory, **options):
    path = os.environ.get('PETREL_DWIN_SOCKET', '')
    if path:
        options.pop('baudrate', None)
        return BrokerSerial(path, **options)
    return factory(port, **options)
