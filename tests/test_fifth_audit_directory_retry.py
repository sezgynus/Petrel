"""CI-only directory retry state through real UI snapshot publication."""
from dataclasses import replace
from unittest.mock import Mock, patch
import unittest

import test_files as files


class DirectoryRetryPublicationTests(unittest.TestCase):
    def view(self):
        v, tree = files.DirectoryBrowserTests().make()
        v._offline = False
        v.last_status = v.pd.status
        v.Draw_Status_Area = Mock()
        v.Redraw_SD_List = Mock()
        v.pd.update_variable = Mock(return_value=False)
        v.pd._file_sort_refresh_at = float('inf')
        v._poll_maintenance_ui = Mock()
        return v, tree

    def fail_next_directory(self, v):
        response = v.pd.getREST.side_effect
        fail = [True]
        def flaky(path):
            if 'directory?' in path and fail[0]:
                fail[0] = False
                raise files.MoonrakerError('temporary directory failure')
            return response(path)
        v.pd.getREST.side_effect = flaky

    def directory_calls(self, v):
        return sum('directory?' in call.args[0] for call in v.pd.getREST.call_args_list)

    def test_new_revision_failure_does_not_publish_empty_and_ui_retries_automatically(self):
        v, tree = self.view()
        old_paths = v._file_paths
        old_revision = v._file_view_revision
        tree['']['files'].append({'filename': 'new.gcode', 'modified': 40, 'size': 5})
        v.pd.state = replace(v.pd.state, file_revision=old_revision+1)
        v.pd._files_loaded = False
        self.fail_next_directory(v)
        with patch('petrel.printer.interface.time.monotonic', return_value=100.):
            v.EachMomentUpdate()
        self.assertTrue(v.pd.file_error)
        self.assertTrue(v.pd._directory_loading)
        self.assertIs(v._file_paths, old_paths)
        requests = self.directory_calls(v)
        for now in (101., 102., 104.9):
            with patch('petrel.printer.interface.time.monotonic', return_value=now):
                v.EachMomentUpdate()
            self.assertIs(v._file_paths, old_paths)
            self.assertEqual(v._file_view_revision, old_revision)
            self.assertTrue(v.pd._directory_loading)
        # General file-list success cleared its error, but not directory readiness.
        self.assertIsNone(v.pd.file_error)
        self.assertEqual(self.directory_calls(v), requests)
        v.Redraw_SD_List.assert_not_called()
        with patch('petrel.printer.interface.time.monotonic', return_value=105.):
            v.EachMomentUpdate()
        self.assertIn('new.gcode', v._file_paths)
        self.assertEqual(v._file_view_revision, old_revision+1)
        self.assertFalse(v.pd._directory_loading)
        self.assertEqual(self.directory_calls(v), requests+1)
        v.Redraw_SD_List.assert_called_once()

    def test_same_revision_folder_entry_failure_keeps_polling_until_success(self):
        v, _ = self.view()
        self.fail_next_directory(v)
        with patch('petrel.printer.interface.time.monotonic', return_value=100.):
            v._enter_file_directory('parts')
        self.assertTrue(v.pd._directory_loading)
        self.assertEqual(v._file_paths, ())
        with patch('petrel.printer.interface.time.monotonic', return_value=101.):
            v.EachMomentUpdate()
        self.assertTrue(v.pd._directory_loading)
        with patch('petrel.printer.interface.time.monotonic', return_value=105.):
            v.EachMomentUpdate()
        self.assertIn('parts/A.gcode', v._file_paths)
        self.assertFalse(v.pd._directory_loading)

    def test_successful_empty_directory_is_complete_and_parent_back_remains_available(self):
        v, _ = self.view()
        v._enter_file_directory('empty')
        self.assertEqual(v._file_paths, ())
        self.assertFalse(v.pd._directory_loading)
        requests = v.pd.getREST.call_count
        v.EachMomentUpdate()
        self.assertEqual(v.pd.getREST.call_count, requests)
        v.select_file.set(0)
        v.HMI_SelectFile()
        self.assertEqual(v._file_directory, '')
        self.assertIn('root.gcode', v._file_paths)

    def test_general_file_list_failure_also_keeps_snapshot_unresolved_through_backoff(self):
        v, _ = self.view()
        old_paths = v._file_paths
        response = v.pd.getREST.side_effect
        fail = [True]
        def flaky(path):
            if path == '/server/files/list' and fail[0]:
                fail[0] = False
                raise files.MoonrakerError('temporary file-list failure')
            return response(path)
        v.pd.getREST.side_effect = flaky
        v.pd._files_loaded = False
        with patch('petrel.printer.interface.time.monotonic', return_value=100.):
            self.assertFalse(v._refresh_file_snapshot())
        requests = v.pd.getREST.call_count
        with patch('petrel.printer.interface.time.monotonic', return_value=101.):
            v.EachMomentUpdate()
        self.assertEqual(v.pd.getREST.call_count, requests)
        self.assertIs(v._file_paths, old_paths)
        self.assertTrue(v.pd._directory_loading)
        with patch('petrel.printer.interface.time.monotonic', return_value=105.):
            v.EachMomentUpdate()
        self.assertFalse(v.pd._directory_loading)
        self.assertIsNone(v.pd.file_error)
