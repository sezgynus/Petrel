import os
import socket
import unittest
from unittest.mock import Mock, patch

from dwin_broker import Broker, FrameQueue, QUEUE_LIMIT, aux_frames, display_frame
from dwin_protocol import HEADER, TAIL
from dwin_transport import BrokerSerial, open_display_serial


class BrokerContracts(unittest.TestCase):
    def test_binary_aux_stream_splits_without_in_band_terminators(self):
        data = bytes(range(256)) * 5 + TAIL * 4 + b'\xaa\x00'
        frames = list(aux_frames(data))
        self.assertEqual(b''.join(frame[2:-4] for frame in frames), data)
        self.assertTrue(all(6 < len(frame) <= 254 for frame in frames))
        self.assertTrue(all(TAIL not in frame[2:-4] for frame in frames))

    def test_ui_cannot_change_or_transmit_on_aux_port(self):
        for data in (b'', HEADER + b'\x38xx' + TAIL,
                     HEADER + b'\x39abc' + TAIL,
                     HEADER + b'\x11' + b'x' * 249 + TAIL):
            with self.assertRaises(ValueError):
                display_frame(data)
        frame = HEADER + b'\x11text' + TAIL
        self.assertEqual(display_frame(frame), frame)

    def test_queue_overflow_is_explicit_and_preserves_accepted_data(self):
        queue = FrameQueue()
        queue.append(b'x' * QUEUE_LIMIT)
        with self.assertRaises(BufferError):
            queue.append(b'y')
        self.assertEqual(queue.pop()[0], b'x' * QUEUE_LIMIT)
        self.assertEqual(queue.size, 0)

    def broker(self):
        broker = Broker.__new__(Broker)
        broker.uart = Mock()
        broker._uart_events = Mock()
        broker.display_tx = FrameQueue()
        broker.aux_tx = FrameQueue()
        broker.active = None
        broker.turn = 0
        return broker

    def test_partial_uart_write_finishes_before_other_channel(self):
        broker = self.broker()
        done = Mock()
        broker.display_tx.append(b'abcdef', done)
        broker.aux_tx.append(b'123')
        broker.uart.write.side_effect = [2, 4, 3]
        broker._transmit()
        done.assert_not_called()
        broker._transmit()
        done.assert_called_once_with()
        broker._transmit()
        self.assertEqual([call.args[0] for call in broker.uart.write.call_args_list],
                         [b'abcdef', b'cdef', b'123'])

    def test_both_channels_make_progress_under_continuous_load(self):
        broker = self.broker()
        for _ in range(3):
            broker.display_tx.append(b'D')
            broker.aux_tx.append(b'A')
        broker.uart.write.return_value = 1
        for _ in range(6):
            broker._transmit()
        self.assertEqual([call.args[0] for call in broker.uart.write.call_args_list],
                         [b'D', b'A', b'D', b'A', b'D', b'A'])

    def test_rx_routes_aux_separately_from_fragmented_display_reply(self):
        broker = self.broker()
        broker.rx = bytearray()
        broker.display_rx = FrameQueue()
        broker.client = object()
        broker.online = True
        broker.auxiliary = Mock()
        broker._client_events = Mock()
        broker.uart.read.side_effect = [HEADER + b'\x32\xa5\x00',
            b'\x10\x02ab' + TAIL + HEADER + b'\x3a\x03xyz' + TAIL]
        broker._receive()
        self.assertFalse(broker.display_rx.frames)
        broker._receive()
        broker.auxiliary.receive.assert_called_once_with(b'xyz')
        self.assertEqual(broker.display_rx.pop()[0],
                         HEADER + b'\x32\xa5\x00\x10\x02ab' + TAIL)


class SocketTransportContracts(unittest.TestCase):
    def test_socket_transport_supports_probe_reads_and_exact_frame_writes(self):
        client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(server.close)
        server.send(b'DWIN1')
        endpoint = Mock(wraps=client)
        endpoint.connect = Mock()
        with patch('dwin_transport.socket.socket', return_value=endpoint):
            transport = BrokerSerial('/unused', timeout=0)
        self.addCleanup(transport.close)
        frame = HEADER + b'\x00' + TAIL
        self.assertEqual(transport.write(frame), len(frame))
        self.assertEqual(server.recv(512), frame)
        server.send(HEADER + b'\x00OK' + TAIL)
        self.assertEqual(transport.in_waiting, 8)
        self.assertEqual(transport.read(3), HEADER + b'\x00O')
        self.assertEqual(transport.read(100), b'K' + TAIL)
        self.assertEqual(transport.in_waiting, 0)
        server.close()
        with self.assertRaises(OSError):
            _ = transport.in_waiting

    def test_unconfigured_transport_preserves_direct_uart(self):
        factory = Mock()
        with patch.dict(os.environ, {'PETREL_DWIN_SOCKET': ''}):
            self.assertIs(open_display_serial('/dev/test', factory, baudrate=115200),
                          factory.return_value)
        factory.assert_called_once_with('/dev/test', baudrate=115200)


if __name__ == '__main__':
    unittest.main()
