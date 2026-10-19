"""CI-only oversized-root prefetch admission and lifecycle regressions."""
from dataclasses import replace
from unittest.mock import Mock
import unittest

from test_capabilities import printer, snapshot
from test_files import MoonrakerError
from test_maintenance_ui_services import DeferredWorker


class OversizedRootPrefetchTests(unittest.TestCase):
    def backend(self):
        p = printer(snapshot())
        p.DIRECTORY_CACHE_BYTES = 256
        p._file_sort_refresh_at = float('inf')
        def response(path):
            if 'directory?' in path:
                return {'result': {'dirs': [], 'files': [
                    {'filename': name, 'metadata': 'x'*1024}
                    for name in ('a.gcode', 'b.gcode')]}}
            return {'result': [{'path': 'a.gcode'}, {'path': 'b.gcode'}]}
        p.getREST = Mock(side_effect=response)
        return p

    def directory_calls(self, p):
        return sum('directory?' in call.args[0] for call in p.getREST.call_args_list)

    def test_pending_then_oversized_root_is_prepared_once_without_retaining_data(self):
        p = self.backend()
        p.GetFiles()
        worker = DeferredWorker()
        p._read_worker = worker
        for _ in range(10):
            p.prefetch_files()
        self.assertEqual(len(worker.work), 1)
        self.assertEqual(self.directory_calls(p), 0)
        worker.run()
        p.prefetch_files()  # Publish the completed read and mark it unretained.
        for _ in range(20):
            p.prefetch_files()
        self.assertEqual(self.directory_calls(p), 1)
        self.assertFalse(worker.work)
        self.assertFalse(p._read_jobs)
        self.assertFalse(p._directory_cache)
        self.assertFalse(p._directory_cache_sizes)
        self.assertFalse(p._directory_orders)
        self.assertEqual(p._root_prefetch_unretained, (p.state.epoch, p.state.file_revision, ''))

    def test_explicit_browsing_refresh_and_sort_still_work_after_prefetch(self):
        p = self.backend()
        p.prefetch_files()
        self.assertEqual(p.GetDirectory(''), ('a.gcode', 'b.gcode'))
        p.file_sort = ('filename', True)
        p.file_sort_revision += 1
        p.GetFiles(refresh=True)
        self.assertEqual(p.GetDirectory(''), ('b.gcode', 'a.gcode'))
        before = self.directory_calls(p)
        for _ in range(10):
            p.prefetch_files()
        self.assertEqual(self.directory_calls(p), before)
        self.assertFalse(p.file_error)
        self.assertFalse(p._directory_cache)
        # If an explicit later read fits, normal cache retention resumes.
        p.DIRECTORY_CACHE_BYTES = 1024*1024
        self.assertEqual(p.GetDirectory(''), ('b.gcode', 'a.gcode'))
        self.assertIsNone(p._root_prefetch_unretained)
        calls = p.getREST.call_count
        p.prefetch_files()
        self.assertEqual(p.getREST.call_count, calls)
        self.assertLessEqual(sum(p._directory_cache_sizes.values()), p.DIRECTORY_CACHE_BYTES)

    def test_new_revision_epoch_and_lifecycle_reset_each_allow_one_new_prefetch(self):
        p = self.backend()
        p.prefetch_files()
        self.assertEqual(self.directory_calls(p), 1)
        p.state = replace(p.state, file_revision=p.state.file_revision+1)
        for _ in range(5):
            p.prefetch_files()
        self.assertEqual(self.directory_calls(p), 2)
        p.state = replace(p.state, epoch=p.state.epoch+1)
        p._invalidate_files()
        self.assertIsNone(p._root_prefetch_unretained)
        for _ in range(5):
            p.prefetch_files()
        self.assertEqual(self.directory_calls(p), 3)
        p._invalidate_files()  # Disconnect cleanup must release the marker too.
        self.assertIsNone(p._root_prefetch_unretained)

    def test_failed_read_is_not_marked_completed_and_can_retry_after_backoff(self):
        p = self.backend()
        response = p.getREST.side_effect
        fail = [True]
        def flaky(path):
            if 'directory?' in path and fail[0]:
                fail[0] = False
                raise MoonrakerError('temporary')
            return response(path)
        p.getREST.side_effect = flaky
        p.prefetch_files()
        self.assertIsNone(p._root_prefetch_unretained)
        self.assertTrue(p.file_error)
        key = (p.state.epoch, p.state.file_revision, '')
        p._directory_retry_at[key] = float('inf')
        p.prefetch_files()
        self.assertEqual(self.directory_calls(p), 1)
        p._directory_retry_at[key] = 0.
        p.prefetch_files()
        self.assertEqual(self.directory_calls(p), 2)
        self.assertEqual(p._root_prefetch_unretained, key)
        self.assertFalse(p.file_error)
