"""Native executable contracts. CI supplies DWIN_C_BROKER; no physical panel."""
import errno
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import tempfile
import time
import unittest

BINARY = os.environ.get('DWIN_C_BROKER')
TAIL = bytes.fromhex('CC 33 C3 3C')
RECORD = struct.Struct('<BIH')


@unittest.skipUnless(BINARY, 'native executable is exercised by the C broker CI job')
class NativeBrokerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.socket_path = str(root / 'display.sock')
        self.backend_path = str(root / 'backend.sock')
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.server.bind(self.backend_path)
        self.server.listen(2)
        self.server.setblocking(False)
        self.addCleanup(self.server.close)
        self.master, self.slave = os.openpty()
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        os.set_blocking(self.master, False)
        self.peer = None
        self.closures = 0
        self.buffer = bytearray()
        self.commands = []
        self.records = []
        self.answer_probes = True
        self.echo = False
        self.log = open(root / 'broker.log', 'w+')
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen([BINARY, '--port', os.ttyname(self.slave),
            '--backend', self.backend_path, '--socket', self.socket_path],
            stdout=self.log, stderr=self.log)
        self.addCleanup(self.cleanup_process)

    def cleanup_process(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        if self.peer is not None:
            self.peer.close()
        self.log.flush()
        self.log.seek(0)
        output = self.log.read()
        self.assertNotIn('AddressSanitizer', output)
        self.assertNotIn('runtime error:', output)
        self.assertEqual(self.process.returncode, 0, output)

    def backend_send(self, op, epoch, payload):
        self.assertIsNotNone(self.peer)
        packet = RECORD.pack(op, epoch, len(payload)) + payload
        self.assertEqual(self.peer.send(packet), len(packet))

    def pump(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            self.assertIsNone(self.process.poll(), 'native broker exited early')
            watched = [self.master, self.server]
            if self.peer is not None:
                watched.append(self.peer)
            readable, _, _ = select.select(watched, [], [], .01)
            for fd in readable:
                if fd is self.server:
                    self.assertIsNone(self.peer)
                    self.peer, _ = self.server.accept()
                    self.peer.setblocking(False)
                    self.backend_send(2, 1, struct.pack('<I', 115200))
                elif fd is self.peer:
                    packet = self.peer.recv(512)
                    if not packet:
                        self.peer.close()
                        self.peer = None
                        self.closures += 1
                    else:
                        self.assertGreaterEqual(len(packet), RECORD.size)
                        op, epoch, size = RECORD.unpack_from(packet)
                        self.assertEqual(len(packet), RECORD.size + size)
                        self.records.append((op, epoch, packet[RECORD.size:]))
                else:
                    try:
                        data = os.read(self.master, 4096)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            continue
                        raise
                    self.buffer.extend(data)
                    while True:
                        start = self.buffer.find(b'\xaa')
                        if start < 0:
                            self.buffer.clear()
                            break
                        if start:
                            del self.buffer[:start]
                        end = self.buffer.find(TAIL, 2)
                        if end < 0:
                            break
                        frame = bytes(self.buffer[:end + 4])
                        del self.buffer[:end + 4]
                        self.commands.append(frame)
                        if frame[1] == 0 and self.answer_probes:
                            os.write(self.master, b'\xaa\x00OK' + TAIL)
                        elif frame[1] == 0x39 and self.echo:
                            payload = frame[2:-4]
                            os.write(self.master, b'\xaa\x3a' + bytes([len(payload)]) + payload + TAIL)
        self.fail('native integration timeout')

    def ready(self):
        self.pump(lambda: any(op == 4 and data == b'\x01' for op, _, data in self.records))

    def connect_ui(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(client.close)
        client.settimeout(1)
        client.connect(self.socket_path)
        self.pump(lambda: bool(select.select([client], [], [], 0)[0]))
        self.assertEqual(client.recv(512), b'DWIN1')
        return client

    def test_binary_tx_rx_baud_and_exact_epoch_ack(self):
        self.ready()
        self.echo = True
        for requested, divisor in ((19200, 816), (57600, 272), (115200, 136)):
            before = len(self.records)
            self.backend_send(2, 5, struct.pack('<I', requested))
            self.pump(lambda: any(op == 4 for op, _, _ in self.records[before:]))
            self.assertIn(b'\xaa\x38' + struct.pack('>H', divisor) + TAIL, self.commands)
        payload = bytes(range(256)) * 4 + TAIL * 10
        total_rx = bytearray()
        for offset in range(0, len(payload), 248):
            part = payload[offset:offset + 248]
            before = len(self.records)
            self.backend_send(1, 123, part)
            self.pump(lambda: any(op == 3 for op, _, _ in self.records[before:]))
            ack = next(item for item in self.records[before:] if item[0] == 3)
            self.assertEqual(ack, (3, 123, struct.pack('<I', len(part))))
        self.pump(lambda: sum(len(data) for op, _, data in self.records if op == 1) == len(payload))
        for op, _, data in self.records:
            if op == 1:
                total_rx.extend(data)
        self.assertEqual(total_rx, payload)
        sent = [frame[2:-4] for frame in self.commands if frame[1] == 0x39]
        self.assertEqual(b''.join(sent), payload)
        self.assertTrue(all(TAIL not in data and len(data) <= 248 for data in sent))
        # Report live memory as evidence, not an architecture-dependent threshold.
        rollup = Path(f'/proc/{self.process.pid}/smaps_rollup').read_text()
        print('Native broker memory:', '; '.join(line for line in rollup.splitlines()
              if line.startswith(('Pss:', 'Private_Clean:', 'Private_Dirty:', 'SwapPss:'))))

    def test_ui_flush_barrier_waits_for_physical_uart_and_does_not_leak(self):
        self.ready()
        client = self.connect_ui()
        first = b'\xaa\x11first' + TAIL
        second = b'\xaa\x11second' + TAIL
        self.assertEqual(client.send(first), len(first))
        self.assertEqual(client.send(second), len(second))
        self.assertEqual(client.send(b'\x00'), 1)
        self.pump(lambda: bool(select.select([client], [], [], 0)[0]))
        # The drain ACK cannot precede either packet reaching physical UART.
        self.assertIn(first, self.commands)
        self.assertIn(second, self.commands)
        self.assertLess(self.commands.index(first), self.commands.index(second))
        self.assertEqual(client.recv(512), b'\x00')
        self.assertNotIn(b'\x00', self.commands)
        followup = b'\xaa\x11after' + TAIL
        client.send(followup)
        self.pump(lambda: followup in self.commands)

    def test_ui_fragmented_length_replies_and_auxiliary_isolation(self):
        self.ready()
        client = self.connect_ui()
        command = b'\xaa\x11hello' + TAIL
        client.send(command)
        self.pump(lambda: command in self.commands)
        payload = b'\xa5\x00\x10\x07' + b'\xaa' + TAIL + b'xy'
        reply = b'\xaa\x32' + payload + TAIL
        for chunk in (b'noise' + reply[:4], reply[4:9], reply[9:]):
            os.write(self.master, chunk)
            until = time.monotonic() + .03
            self.pump(lambda: time.monotonic() >= until, timeout=1)
        os.write(self.master, b'\xaa\x3a\x03xyz' + TAIL)
        self.pump(lambda: bool(select.select([client], [], [], 0)[0]) and
                  any(op == 1 and data == b'xyz' for op, _, data in self.records))
        self.assertEqual(client.recv(512), reply)
        self.assertFalse(select.select([client], [], [], 0)[0])
        second = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(second.close)
        second.connect(self.socket_path)
        self.pump(lambda: bool(select.select([second], [], [], 0)[0]))
        self.assertEqual(second.recv(10), b'')

    def test_invalid_reserved_and_oversized_ui_packets_drop_only_ui(self):
        self.ready()
        for packet in (b'bad', b'\xaa\x38xx' + TAIL, b'\xaa\x39abc' + TAIL,
                       b'\xaa\x11' + b'x' * 300 + TAIL):
            client = self.connect_ui()
            client.send(packet)
            self.pump(lambda: bool(select.select([client], [], [], 0)[0]))
            self.assertEqual(client.recv(512), b'')
            client.close()
        self.assertEqual(self.closures, 0)
        self.backend_send(1, 15, b'still works')
        self.pump(lambda: (3, 15, struct.pack('<I', 11)) in self.records)

    def test_heartbeat_loss_hangs_up_then_recovers_without_replay(self):
        self.ready()
        client = self.connect_ui()
        self.answer_probes = False
        self.pump(lambda: self.closures > 0, timeout=5)
        self.assertEqual(client.recv(512), b'')
        client.close()
        self.answer_probes = True
        before = len(self.records)
        self.pump(lambda: any(op == 4 for op, _, _ in self.records[before:]), timeout=5)
        recovered = self.connect_ui()
        command = b'\xaa\x11recovered' + TAIL
        recovered.send(command)
        self.pump(lambda: command in self.commands)
        self.assertFalse(any(frame[1] == 0x39 for frame in self.commands))

    def test_malformed_kernel_record_disconnects_transport(self):
        self.ready()
        client = self.connect_ui()
        self.peer.send(RECORD.pack(1, 7, 5) + b'x')
        self.pump(lambda: self.closures > 0)
        self.assertEqual(client.recv(512), b'')

    def test_existing_socket_path_and_cli_validation(self):
        path = Path(self.directory.name) / 'owned-file'
        path.write_text('must survive')
        for args, code in ((['--help'], 0), ([], 2),
                           (['--port', '/dev/null', '--unknown'], 2),
                           (['--port', '/dev/null', 'unexpected'], 2),
                           (['--port', '/dev/null', '--socket', str(path)], 1)):
            result = subprocess.run([BINARY, *args], text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(path.read_text(), 'must survive')


if __name__ == '__main__':
    unittest.main()
