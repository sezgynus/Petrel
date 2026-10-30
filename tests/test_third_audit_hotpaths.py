"""CI-only preview cadence and retry-backoff allocation regressions."""
from concurrent.futures import Future
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import unittest

import test_files as files
from petrel.features.files.thumbnail_preview import NoThumbnail
from petrel.ui.events import UIEventLoop


class ThirdAuditHotpaths(unittest.TestCase):
    def view(self):
        v = files.FileTests().display(['%02d.gcode'%i for i in range(9)])
        del v._open_file_preview
        v._loop = UIEventLoop(lambda: None, lambda e: None, lambda: None, lambda: None)
        v._uart_online = True
        v._boot_active = False
        v._poll_panel_power = Mock()
        v._sync_case_light_tracking = Mock()
        v._power_hold_tick = Mock(return_value=False)
        v._power_popup_tick = Mock(return_value=False)
        v._next_uart_probe = float('inf')
        v._display_idle_tick = Mock()
        v._draw_header_clock = Mock(return_value=False)
        v.EachMomentUpdate = Mock()
        v.pd.maintenance_pulse = NS(pending=False)
        v.pd.maintenance_reader = NS(pending=False)
        v._thumbnail_cache.job = None
        future = Future()
        v._thumbnail_cache.loader = Mock(return_value=future)
        v._open_file_preview(v._file_paths[5])
        return v, future

    def test_foreground_load_and_upload_are_fast_then_idle_despite_background_work(self):
        v, future = self.view()
        v._ui_tick()
        self.assertEqual(v._loop._interval, .02)
        future.set_result(b'x'*1600)
        v._ui_tick()
        self.assertIsNotNone(v._thumbnail_cache.upload)
        self.assertEqual(v._loop._interval, .02)
        v._ui_tick()
        self.assertTrue(v._preview_shown)
        self.assertTrue(v._thumbnail_cache.has_work())  # Unrelated preload backlog.
        self.assertEqual(v._loop._interval, .5)
        v.lcd.reset_mock()
        for _ in range(3):
            v._ui_tick()
        v.lcd.write_sram.assert_not_called()
        v.lcd.show_sram_jpeg.assert_not_called()
        self.assertEqual(v._thumbnail_cache.loader.call_count, 1)

    def test_permanent_absence_sleeps_and_maintenance_still_caps_interval(self):
        v, future = self.view()
        future.set_exception(NoThumbnail('No thumbnail'))
        v._ui_tick()
        self.assertEqual(v._loop._interval, .5)
        v._ui_tick()
        self.assertEqual(v._thumbnail_cache.loader.call_count, 1)
        v.pd.maintenance_pulse.pending = True
        v.pd.update_variable = Mock(return_value=False)
        v._advance_maintenance_operations = Mock()
        v._ui_tick()
        self.assertEqual(v._loop._interval, .1)
        v._advance_maintenance_operations.assert_called_once()

    def test_transient_retry_waits_at_idle_cadence_and_resumes_foreground_loading(self):
        v, future = self.view()
        future.set_exception(ValueError('temporary'))
        with patch('petrel.features.files.thumbnail_cache.time.monotonic', return_value=100.):
            v._ui_tick()
        self.assertEqual(v._loop._interval, .5)
        with patch('petrel.features.files.thumbnail_cache.time.monotonic', return_value=109.):
            v._ui_tick()
        self.assertEqual(v._thumbnail_cache.loader.call_count, 1)
        retry = Future()
        v._thumbnail_cache.loader.return_value = retry
        with patch('petrel.features.files.thumbnail_cache.time.monotonic', return_value=110.):
            v._ui_tick()
        self.assertEqual(v._thumbnail_cache.loader.call_count, 2)
        self.assertEqual(v._loop._interval, .02)
        retry.set_result(b'x'*100)
        v._ui_tick()
        self.assertTrue(v._preview_shown)
        self.assertEqual(v._loop._interval, .5)

    def test_failed_refresh_backoff_reuses_paths_without_traversing_old_files(self):
        class NoScan(list):
            def __iter__(self):
                raise AssertionError('UI scanned the retained file list')
        p = files.FileTests().backend(['%05d.gcode'%i for i in range(5000)])
        paths = p._files_paths_snapshot
        p._file_sort_refresh_at = float('inf')
        p.getREST.reset_mock()
        p.getREST.side_effect = files.MoonrakerError('timeout')
        self.assertIs(p.GetFiles(refresh=True), paths)
        p.files = NoScan(p.files)
        p._file_retry_at = float('inf')
        for _ in range(10):
            self.assertIs(p.GetFiles(), paths)
            self.assertEqual(p.GetDirectory(), ())
            p.prefetch_files()
        p.getREST.assert_called_once()
        self.assertTrue(p.file_error)
        self.assertFalse(p._files_loaded)
