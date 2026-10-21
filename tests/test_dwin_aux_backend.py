import struct
import unittest
from unittest.mock import Mock, patch

from dwin_aux_backend import AuxBackend, RECORD, decode, record
from dwin_broker import FrameQueue
from dwin_protocol import HEADER, TAIL


class KernelAdapterTests(unittest.TestCase):
    def adapter(self):
        adapter = AuxBackend()
        adapter.fd = 4
        adapter.selector = Mock()
        adapter.needs_configuration = False
        broker = Mock(online=True, aux_tx=FrameQueue())
        broker.uart.out_waiting = 0
        return adapter, broker

    def test_record_length_mismatch_is_rejected(self):
        self.assertEqual(decode(record(1, 32, b'abc')), (1, 32, b'abc'))
        for data in (b'', RECORD.pack(1, 0, 2) + b'x', record(1, 0, b'x' * 249)):
            with self.assertRaises(ValueError):
                decode(data)

    def test_baud_record_programs_panel_before_marking_tty_ready(self):
        adapter, broker = self.adapter()
        with patch('dwin_aux_backend.os.read', return_value=record(2, 1, struct.pack('<I', 19200))), \
                patch('dwin_aux_backend.os.write') as write:
            adapter.poll(broker)
            write.assert_not_called()
            frame, complete = broker.aux_tx.pop()
            self.assertEqual(frame, bytes.fromhex('AA 38 03 30 CC 33 C3 3C'))
            write.return_value = 8
            complete()
            write.assert_called_once_with(4, record(4, 0, b'\x01'))

    def test_tx_completion_waits_for_serialization_and_keeps_epoch(self):
        adapter, broker = self.adapter()
        with patch('dwin_aux_backend.os.read', return_value=record(1, 7, b'abc')), \
                patch('dwin_aux_backend.time.monotonic', return_value=1):
            adapter.poll(broker)
            frame, complete = broker.aux_tx.pop()
            self.assertEqual(frame, HEADER + b'\x39abc' + TAIL)
            complete()
        deadline = adapter.completion[0]
        self.assertGreater(deadline, 1)
        with patch('dwin_aux_backend.time.monotonic', return_value=1), \
                patch('dwin_aux_backend.os.write') as write:
            adapter.poll(broker)
            write.assert_not_called()
        with patch('dwin_aux_backend.time.monotonic', return_value=deadline + .01), \
                patch('dwin_aux_backend.os.read', side_effect=BlockingIOError), \
                patch('dwin_aux_backend.os.write', return_value=11) as write:
            adapter.poll(broker)
            write.assert_called_once_with(4, record(3, 7, struct.pack('<I', 3)))

    def test_partial_kernel_rx_acceptance_retains_remaining_bytes(self):
        adapter, broker = self.adapter()
        adapter.receive(b'abcdef')
        with patch('dwin_aux_backend.os.read', side_effect=BlockingIOError), \
                patch('dwin_aux_backend.os.write', return_value=RECORD.size + 2):
            adapter.poll(broker)
        self.assertEqual(adapter.rx, b'cdef')

    def test_rx_capacity_exhaustion_is_explicit(self):
        adapter = AuxBackend()
        adapter.receive(b'x' * 65536)
        with self.assertRaises(BufferError):
            adapter.receive(b'x')


if __name__ == '__main__':
    unittest.main()
