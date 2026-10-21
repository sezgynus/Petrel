"""Single owner of the panel UART, independent of Petrel's UI lifecycle.

Unix SEQPACKET carries exactly one complete display command per message.
Auxiliary traffic has its own bounded queue; scheduling never interleaves bytes
inside a panel frame. Kernel TTY backend integration is isolated in AuxBackend.
"""
import argparse
from collections import deque
import logging
import os
import selectors
import socket
import time

import serial
from dwin_protocol import HEADER, TAIL, MAX_DATA_LENGTH, take_response

LOG = logging.getLogger(__name__)
QUEUE_LIMIT = 65536


class FrameQueue:
    def __init__(self):
        self.frames = deque()
        self.size = 0

    def append(self, frame, complete=None):
        if self.size + len(frame) > QUEUE_LIMIT:
            raise BufferError('DWIN queue capacity exceeded')
        self.frames.append((frame, complete))
        self.size += len(frame)

    def pop(self):
        frame, complete = self.frames.popleft()
        self.size -= len(frame)
        return frame, complete


def display_frame(data):
    if (not 6 <= len(data) <= MAX_DATA_LENGTH + 6
            or not data.startswith(HEADER) or not data.endswith(TAIL)
            or data[1] in (0x38, 0x39)):
        raise ValueError('Invalid or reserved display command')
    return data


def aux_frames(data):
    """Split arbitrary binary streams, including in-band frame terminators."""
    while data:
        part = data[:MAX_DATA_LENGTH]
        marker = part.find(TAIL)
        if marker >= 0:
            part = part[:marker + len(TAIL) - 1]
        yield HEADER + b'\x39' + part + TAIL
        data = data[len(part):]


class Broker:
    def __init__(self, port, path, auxiliary=None):
        self.port = port
        self.path = path
        self.auxiliary = auxiliary
        self.selector = selectors.DefaultSelector()
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        # RuntimeDirectory is private to this service. Never unlink arbitrary paths.
        if os.path.lexists(path):
            raise FileExistsError(path)
        self.listener.bind(path)
        os.chmod(path, 0o660)
        self.listener.listen(2)
        self.listener.setblocking(False)
        self.selector.register(self.listener, selectors.EVENT_READ, 'accept')
        self.uart = None
        self.client = None
        self.display_tx = FrameQueue()
        self.aux_tx = FrameQueue()
        self.display_rx = FrameQueue()
        self.rx = bytearray()
        self.active = None
        self.turn = 0
        self.online = False
        self.probe_at = 0
        self.probe_deadline = None
        self.reconnect_at = 0

    def _accept(self):
        conn, _ = self.listener.accept()
        conn.setblocking(False)
        if self.client is not None or not self.online:
            conn.close()
            return
        self.client = conn
        self.selector.register(conn, selectors.EVENT_READ, 'client')
        self.display_rx.append(b'DWIN1')
        self._client_events()

    def _client_events(self):
        if self.client is not None:
            self.selector.modify(self.client, selectors.EVENT_READ |
                                 (selectors.EVENT_WRITE if self.display_rx.frames else 0), 'client')

    def _drop_client(self):
        if self.client is not None:
            self.selector.unregister(self.client)
            self.client.close()
            self.client = None
        self.display_rx = FrameQueue()
        self.display_tx = FrameQueue()
        # A partly written frame must finish; never splice another frame into it.

    def _disconnect(self):
        self._drop_client()
        if self.uart is not None:
            self.selector.unregister(self.uart.fileno())
            self.uart.close()
            self.uart = None
        self.online = False
        self.rx.clear()
        self.active = None
        self.aux_tx = FrameQueue()
        self.probe_deadline = None
        self.reconnect_at = time.monotonic() + 1
        if self.auxiliary is not None:
            self.auxiliary.disconnected()

    def _uart_events(self):
        self.selector.modify(self.uart.fileno(), selectors.EVENT_READ |
                             (selectors.EVENT_WRITE if self.active is not None
                              or self.display_tx.frames or self.aux_tx.frames else 0), 'uart')

    def _transmit(self):
        if self.active is None:
            queues = (self.display_tx, self.aux_tx)
            queue = queues[self.turn] if queues[self.turn].frames else queues[1 - self.turn]
            if not queue.frames:
                return
            self.active = queue.pop()
            self.turn = 1 - self.turn
        data, complete = self.active
        count = self.uart.write(data)
        self.active = (data[count:], complete)
        if count == len(data):
            self.active = None
            if complete is not None:
                complete()
        self._uart_events()

    def _receive(self):
        self.rx.extend(self.uart.read(4096))
        while True:
            response = take_response(self.rx)
            if response is None:
                break
            command, payload = response
            if command == 0x00 and payload == b'OK':
                was_online = self.online
                self.online = True
                self.probe_deadline = None
                if not was_online and self.auxiliary is not None:
                    self.auxiliary.connected()
            if command == 0x3a:
                if self.auxiliary is not None and self.online:
                    self.auxiliary.receive(payload[1:])
            elif self.client is not None:
                self.display_rx.append(HEADER + bytes([command]) + payload + TAIL)
        self._client_events()

    def step(self, timeout=.1):
        now = time.monotonic()
        if self.uart is None and now >= self.reconnect_at:
            try:
                self.uart = serial.Serial(self.port, 115200, timeout=0,
                                          write_timeout=0, exclusive=True)
                self.selector.register(self.uart.fileno(), selectors.EVENT_READ, 'uart')
                self.probe_at = 0
            except OSError:
                self.reconnect_at = now + 1
        if self.uart is not None:
            if self.probe_deadline is not None and now >= self.probe_deadline:
                self._disconnect()
            elif now >= self.probe_at:
                # Reserve timeout from actual transmission, not time in the queue.
                def sent():
                    self.probe_deadline = time.monotonic() + 1
                self.display_tx.append(HEADER + b'\x00' + TAIL, sent)
                self.probe_at = now + 2
                self._uart_events()
        if self.auxiliary is not None:
            self.auxiliary.poll(self)
        for key, events in self.selector.select(timeout):
            try:
                if key.data == 'accept':
                    self._accept()
                elif key.data == 'client' and key.fileobj is self.client:
                    if events & selectors.EVENT_READ:
                        data = self.client.recv(MAX_DATA_LENGTH + 7)
                        if not data:
                            self._drop_client()
                            continue
                        self.display_tx.append(display_frame(data))
                        if self.uart is not None:
                            self._uart_events()
                    if events & selectors.EVENT_WRITE and self.client is not None:
                        data, _ = self.display_rx.frames[0]
                        if self.client.send(data) != len(data):
                            raise OSError('Partial display response')
                        self.display_rx.pop()
                        self._client_events()
                elif key.data == 'uart' and self.uart is not None:
                    if events & selectors.EVENT_READ:
                        self._receive()
                    if events & selectors.EVENT_WRITE and self.uart is not None:
                        self._transmit()
            except BlockingIOError:
                continue
            except (OSError, BufferError, ValueError):
                LOG.exception('DWIN connection failed (%s)', key.data)
                if key.data == 'client':
                    self._drop_client()
                else:
                    self._disconnect()

    def close(self):
        self._disconnect()
        if self.auxiliary is not None:
            self.auxiliary.close()
        self.selector.close()
        self.listener.close()
        os.unlink(self.path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--socket', default='/run/petrel-dwin/display.sock')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    broker = Broker(args.port, args.socket)
    try:
        while True:
            broker.step()
    except KeyboardInterrupt:
        pass
    finally:
        broker.close()


if __name__ == '__main__':
    main()
