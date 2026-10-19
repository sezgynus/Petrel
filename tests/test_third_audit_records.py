"""CI-only byte retention and non-expiring local result regressions."""
from pathlib import Path
from threading import Event, current_thread
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import tempfile
import unittest

from background_reads import ReadWorker, MoonrakerError
import maintenance_records as records
from maintenance_records import MaintenanceBook, read_json
from test_maintenance_ui_services import DeferredWorker


class ThirdAuditRecords(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        context = patch('maintenance_records.root', return_value=self.folder)
        context.start()
        self.addCleanup(context.stop)
        self.state = NS(settings={}, epoch=1, software_version='test')

    def result(self, index=0, wide=False):
        pairs = tuple(('key_%02d'%i + 'k'*40, 'v'*96) for i in range(16)) if wide else ()
        return NS(feature_id='F01', device='fan', status='PASSED_USER', reason='observed',
                  evidence=pairs, conditions=pairs, operation_id='op%d'%index)

    def save(self, book, worker, result):
        book.record(result, 2, self.state)
        worker.run()
        book.poll_records()

    def test_wide_valid_results_keep_newest_group_within_byte_limit_and_continue(self):
        worker = DeferredWorker()
        book = MaintenanceBook(worker)
        for index in range(30):
            self.save(book, worker, self.result(index, wide=True))
        group = NS(components=tuple(self.result(30+i, wide=True) for i in range(7)))
        self.save(book, worker, group)
        path = self.folder/'maintenance-history.json'
        saved = read_json(path.name, {})['records']
        self.assertLessEqual(path.stat().st_size, records.MAX_RECORD_BYTES)
        self.assertLess(len(saved), 37)
        self.assertEqual([r['operation_id'] for r in saved[-7:]], ['op%d'%i for i in range(30,37)])
        self.assertTrue(all(len(r['evidence']) == len(r['conditions']) == 16 for r in saved))
        self.save(book, worker, self.result(37, wide=True))
        self.assertEqual(read_json(path.name, {})['records'][-1]['operation_id'], 'op37')
        self.assertEqual(book.errors, 0)

    def test_count_limit_still_keeps_latest_64_small_results(self):
        worker = DeferredWorker()
        book = MaintenanceBook(worker)
        for index in range(65):
            self.save(book, worker, self.result(index))
        saved = read_json('maintenance-history.json', {})['records']
        self.assertEqual(len(saved), 64)
        self.assertEqual(saved[0]['operation_id'], 'op1')
        self.assertEqual(saved[-1]['operation_id'], 'op64')

    def test_unsplittable_new_group_is_reported_without_changing_old_history(self):
        worker = DeferredWorker()
        book = MaintenanceBook(worker)
        self.save(book, worker, self.result())
        path = self.folder/'maintenance-history.json'
        previous = path.read_bytes()
        group = NS(components=tuple(self.result(i) for i in range(7)))
        with patch('maintenance_records.MAX_RECORD_BYTES', 1024), self.assertLogs(level='WARNING'):
            self.save(book, worker, group)
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(book.errors, 1)
        self.save(book, worker, self.result(10))
        self.assertEqual(read_json(path.name, {})['records'][-1]['operation_id'], 'op10')

    def test_accepted_local_result_survives_queue_age_while_network_reads_expire(self):
        worker = ReadWorker(timeout=.01)
        entered, release = Event(), Event()
        self.addCleanup(worker.close)
        self.addCleanup(release.set)
        clock = [0.]
        def block():
            entered.set()
            release.wait(3)
        writes = []
        original = records.write_json
        def write(name, value):
            writes.append((name, current_thread()))
            return original(name, value)
        with patch('background_reads.monotonic', side_effect=lambda: clock[0]), patch(
                'maintenance_records.write_json', side_effect=write):
            first = worker.submit(block)
            self.assertTrue(entered.wait(1))
            stale_work = Mock()
            stale = worker.submit(stale_work, queue_timeout=8)
            book = MaintenanceBook(worker)
            book.record(self.result(), 2, self.state)
            result_future = book._record_futures[0]
            clock[0] = 100.
            release.set()
            first.result(1)
            self.assertIsInstance(stale.exception(1), MoonrakerError)
            result_future.result(1)
            book.poll_records()
            book.close()
        stale_work.assert_not_called()
        history_writes = [owner for name, owner in writes if name == 'maintenance-history.json']
        self.assertEqual(len(history_writes), 1)
        self.assertIsNot(history_writes[0], current_thread())
        self.assertEqual(len(read_json('maintenance-history.json', {})['records']), 1)
        self.assertEqual(book.errors, 0)
