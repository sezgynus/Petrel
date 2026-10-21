import struct
import subprocess
import sys
import textwrap
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from dwin_aux_backend import AuxBackend, RECORD, decode, record
from dwin_broker import FrameQueue
from dwin_protocol import HEADER, TAIL


class KernelAdapterTests(unittest.TestCase):
    def adapter(self):
        adapter = AuxBackend()
        adapter.fd = 4
        adapter.watching = True
        adapter.tty_ready = True
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

    def test_split_binary_record_acknowledges_only_after_last_frame(self):
        adapter, broker = self.adapter()
        payload = TAIL * 60
        with patch('dwin_aux_backend.os.read', return_value=record(1, 17, payload)), \
                patch('dwin_aux_backend.time.monotonic', return_value=1):
            adapter.poll(broker)
            received = bytearray()
            self.assertGreater(len(broker.aux_tx.frames), 1)
            while broker.aux_tx.frames:
                frame, complete = broker.aux_tx.pop()
                self.assertNotIn(TAIL, frame[2:-4])
                received.extend(frame[2:-4])
                complete()
                if broker.aux_tx.frames:
                    self.assertEqual(adapter.completion[0], float('inf'))
            self.assertEqual(received, payload)
        deadline, epoch, count = adapter.completion
        self.assertEqual((epoch, count), (17, len(payload)))
        with patch('dwin_aux_backend.time.monotonic', return_value=deadline + .01), \
                patch('dwin_aux_backend.os.read', side_effect=BlockingIOError), \
                patch('dwin_aux_backend.os.write', return_value=11) as write:
            adapter.poll(broker)
            write.assert_called_once_with(4, record(3, 17, struct.pack('<I', len(payload))))

    def test_script_namespace_tx_does_not_import_a_second_broker_module(self):
        # Isolate sys.modules: normal unit imports already cache dwin_broker and
        # would conceal the duplicate load caused by the service script entry.
        script = textwrap.dedent('''
            import runpy, sys
            from unittest.mock import Mock, patch
            from dwin_aux_backend import AuxBackend, record
            namespace = runpy.run_path('dwin_broker.py', run_name='service_entry')
            assert 'dwin_broker' not in sys.modules
            backend = AuxBackend()
            backend.fd = 4
            backend.watching = backend.tty_ready = True
            backend.selector = Mock()
            backend.needs_configuration = False
            broker = Mock(online=True, aux_tx=namespace['FrameQueue']())
            broker.uart.out_waiting = 0
            with patch('dwin_aux_backend.os.read', return_value=record(1, 7, b'abc')):
                backend.poll(broker)
            assert broker.aux_tx.pop()[0] == bytes.fromhex('AA 39 61 62 63 CC 33 C3 3C')
            assert 'dwin_broker' not in sys.modules, 'broker was loaded twice'
        ''')
        result = subprocess.run([sys.executable, '-c', script],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_busy_tx_unsubscribes_readable_backend_until_completion(self):
        adapter, broker = self.adapter()
        with patch('dwin_aux_backend.os.read', return_value=record(1, 7, b'abc')):
            adapter.poll(broker)
        adapter.selector.unregister.assert_called_once_with(4)
        self.assertFalse(adapter.watching)
        adapter.completion = (0, 7, 3)
        with patch('dwin_aux_backend.os.read', side_effect=BlockingIOError), \
                patch('dwin_aux_backend.os.write', return_value=11):
            adapter.poll(broker)
        adapter.selector.register.assert_called_once_with(4, 1, 'backend')

    def test_startup_rx_waits_until_kernel_port_is_ready(self):
        adapter, broker = self.adapter()
        adapter.tty_ready = False
        adapter.receive(b'early streaming data')
        with patch('dwin_aux_backend.os.read', side_effect=BlockingIOError), \
                patch('dwin_aux_backend.os.write') as write:
            adapter.poll(broker)
        write.assert_not_called()
        self.assertEqual(adapter.rx, b'early streaming data')
        broker._disconnect.assert_not_called()

    def test_rx_capacity_exhaustion_is_explicit(self):
        adapter = AuxBackend()
        adapter.receive(b'x' * 65536)
        with self.assertRaises(BufferError):
            adapter.receive(b'x')


if __name__ == '__main__':
    unittest.main()
