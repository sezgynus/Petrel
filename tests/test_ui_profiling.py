import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import ui_memory_profile as memory
from tools import profile_ui_resources as resources


class MemoryProfileTests(unittest.TestCase):
    def test_real_worker_writes_report_and_releases_tracer(self):
        with tempfile.TemporaryDirectory() as directory:
            code = '''
import json, pathlib, sys, tracemalloc
from ui_memory_profile import start_from_environment
worker = start_from_environment({
    'PETREL_PROFILE_MEMORY_DIR': sys.argv[1],
    'PETREL_PROFILE_WARMUP_SECONDS': '1', 'PETREL_PROFILE_SECONDS': '1'})
assert worker is not None
worker.join(15)
assert not worker.is_alive()
assert not tracemalloc.is_tracing()
reports = list(pathlib.Path(sys.argv[1]).glob('memory-*.json'))
assert len(reports) == 1
report = json.loads(reports[0].read_text())
assert report['schema'] == 1 and report['instrumented']
assert report['window_seconds'] >= 1
assert len(report['retained_by_traceback']) <= 40
'''
            subprocess.run([sys.executable, '-c', code, directory],
                           cwd=Path(__file__).resolve().parents[1], check=True, timeout=25)

    def test_disabled_does_not_start_tracing(self):
        with patch.object(memory.tracemalloc, 'start') as start:
            self.assertIsNone(memory.start_from_environment({}))
        start.assert_not_called()

    def test_invalid_bounds_do_not_start_tracing(self):
        for value in ('nan', 'inf', '-1', '0', '601', 'no'):
            with self.subTest(value=value), self.assertLogs(level='ERROR'), \
                    patch.object(memory.tracemalloc, 'start') as start:
                self.assertIsNone(memory.start_from_environment({
                    'PETREL_PROFILE_MEMORY_DIR': '/unused',
                    'PETREL_PROFILE_SECONDS': value}))
            start.assert_not_called()

    def test_does_not_take_over_another_tracer(self):
        with patch.object(memory.tracemalloc, 'is_tracing', return_value=True), \
                patch.object(memory.tracemalloc, 'stop') as stop, self.assertLogs(level='ERROR'):
            self.assertIsNone(memory.start_from_environment({'PETREL_PROFILE_MEMORY_DIR': '/unused'}))
        stop.assert_not_called()

    def test_capture_failure_stops_owned_tracer(self):
        with patch.object(memory.time, 'sleep'), \
                patch.object(memory.tracemalloc, 'take_snapshot', side_effect=RuntimeError('fail')), \
                patch.object(memory.tracemalloc, 'stop') as stop:
            with self.assertRaises(RuntimeError):
                memory.capture('/unused', 1, 1)
        stop.assert_called_once()

    def test_report_is_private_and_captures_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            first = memory.write_report(directory, {'schema': 1})
            second = memory.write_report(directory, {'schema': 2})
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text()), {'schema': 1})
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list(Path(directory).iterdir())), 2)

    def test_rows_are_bounded_and_do_not_include_values(self):
        stat = SimpleNamespace(size=24, count=2, size_diff=-8, count_diff=-1,
                               traceback=[SimpleNamespace(filename='sample.py', lineno=12)])
        rows = memory.allocation_rows([stat] * 100)
        self.assertEqual(len(rows), 40)
        self.assertEqual(rows[0], {'bytes': 24, 'count': 2, 'bytes_diff': -8,
                                  'count_diff': -1,
                                  'traceback': [{'file': 'sample.py', 'line': 12}]})

    def test_capture_records_retention_and_stops_before_writing(self):
        baseline, final = SimpleNamespace(), SimpleNamespace(
            statistics=lambda key: [], compare_to=lambda previous, key: [])
        order = []
        with patch.object(memory.time, 'sleep'), \
                patch.object(memory.tracemalloc, 'take_snapshot', side_effect=[baseline, final]), \
                patch.object(memory.tracemalloc, 'reset_peak'), \
                patch.object(memory.tracemalloc, 'get_traced_memory', return_value=(20, 30)), \
                patch.object(memory.tracemalloc, 'get_tracemalloc_memory', return_value=10), \
                patch.object(memory.tracemalloc, 'stop', side_effect=lambda: order.append('stop')), \
                patch.object(memory, 'write_report', side_effect=lambda d, r: order.append(r)):
            memory.capture('/unused', 1, 1)
        self.assertEqual(order[0], 'stop')
        self.assertEqual(order[1]['traced_current_bytes'], 20)
        self.assertTrue(order[1]['instrumented'])


class ResourceProfileTests(unittest.TestCase):
    def test_service_pid_zero_has_actionable_error(self):
        with patch.object(resources.subprocess, 'check_output', return_value='0\n'):
            with self.assertRaisesRegex(ValueError, 'MainPID=0'):
                resources.service_pid('Petrel.service')

    def test_process_identity_handles_spaces_and_parentheses(self):
        fields = ['S'] + ['0'] * 18 + ['123456'] + ['0'] * 5
        with patch.object(Path, 'read_text', return_value='42 (odd ) name) ' + ' '.join(fields)):
            self.assertEqual(resources.process_identity(42), '123456')

    def test_restart_is_rejected(self):
        with patch.object(resources, 'service_pid', return_value=43):
            with self.assertRaisesRegex(RuntimeError, 'restarted'):
                resources.assert_same_process('Petrel.service', 42, '100')

    def test_pid_reuse_is_rejected(self):
        with patch.object(resources, 'service_pid', return_value=42), \
                patch.object(resources, 'process_identity', return_value='101'):
            with self.assertRaisesRegex(RuntimeError, 'restarted'):
                resources.assert_same_process('Petrel.service', 42, '100')

    def test_swap_is_included_in_total(self):
        smaps = ('Rss: 3000 kB\nPss: 2400 kB\nPrivate_Clean: 50 kB\n'
                 'Private_Dirty: 900 kB\nSwap: 600 kB\nSwapPss: 500 kB\n')
        stat = '42 (petrel) ' + ' '.join(['S'] + ['0'] * 25)
        with patch.object(Path, 'read_text', side_effect=[smaps, stat]):
            sample = resources.read_sample(42)
        self.assertEqual(sample['memory_kib']['Pss_plus_SwapPss'], 2900)
        self.assertEqual(sample['memory_kib']['USS'], 950)

    def test_duration_rejects_nonfinite_values_before_pid_lookup(self):
        for value in ('nan', 'inf', '0', '601'):
            with self.subTest(value=value), patch.object(resources, 'service_pid') as pid, \
                    patch('sys.stderr'), self.assertRaises(SystemExit):
                resources.main(['baseline', '--seconds', value, '--label', 'idle',
                                '--output-dir', '/unused'])
            pid.assert_not_called()


if __name__ == '__main__':
    unittest.main()
