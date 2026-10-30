"""Second-audit foreground identity and safe thumbnail budget regressions (CI)."""
from concurrent.futures import Future
from dataclasses import replace
from unittest.mock import Mock
import unittest
import test_files as files
from test_thumbnail_preview import png
from petrel.features.files.thumbnail_preview import load_preview, MAX_CANDIDATES


class ReauditPreviewTests(unittest.TestCase):
    def view(self):
        v=files.FileTests().display(['%02d.gcode'%i for i in range(9)])
        del v._open_file_preview
        v._thumbnail_cache.job=None
        v._thumbnail_cache.loader=Mock(return_value=Future())
        v._loop=Mock()
        return v

    def test_cold_sixth_and_later_preview_load_without_list_refresh(self):
        v=self.view();original_files=v.pd.files
        for index in (5,8,6):
            path=v._file_paths[index]
            v._thumbnail_cache.job=None
            v._thumbnail_cache.loader.reset_mock()
            v._open_file_preview(path)
            self.assertIs(v.pd.files,original_files)
            self.assertIn(v._preview_cache_key,v._thumbnail_cache.valid)
            self.assertIsNone(v._preview_error)
            v._thumbnail_cache.loader.assert_called_once_with(v._thumbnail_keys[path])
            self.assertEqual(v._preview_choice,1)
            self.assertEqual(v._thumbnail_cache.priority,tuple(v._thumbnail_keys[p] for p in v._file_paths[:5]))

    def test_real_replacement_and_deletion_remain_invalid(self):
        for removed in (False,True):
            v=self.view();path=v._file_paths[5];v._open_file_preview(path)
            old=v._preview_cache_key
            v.pd.getREST.return_value={'result':[{'path':p,'modified':2,'size':200}
                for p in v._file_paths if not (removed and p==path)]}
            v.pd.state=replace(v.pd.state,file_revision=v.pd.state.file_revision+1)
            v.pd.GetFiles(refresh=True)
            v._poll_file_preview()
            self.assertNotIn(old,v._thumbnail_cache.valid)
            self.assertEqual(v._preview_error,'File changed; select again')
            v.pd.openAndPrintFile=Mock()
            v._preview_validation=True
            v._poll_preview_validation()
            v.pd.openAndPrintFile.assert_not_called()

    def test_unsafe_paths_do_not_consume_download_budget(self):
        client=Mock()
        unsafe=[{'relative_path':'../../bad%d'%i,'width':128,'height':128} for i in range(8)]
        good={'relative_path':'.thumbs/good.png','width':128,'height':128}
        client.get.return_value={'result':{'thumbnails':unsafe+[good]}}
        client.get_bytes.return_value=png()
        result=load_preview(client,'parts/model.gcode')
        self.assertTrue(result.jpeg.startswith(b'\xff\xd8'))
        client.get_bytes.assert_called_once_with('/server/files/gcodes/parts/.thumbs/good.png',max_bytes=2_000_000)

    def test_exhausted_download_budget_remains_transient_not_absence(self):
        client=Mock();client.get.return_value={'result':{'thumbnails':[
            {'relative_path':str(i)+'.png','width':128,'height':128} for i in range(8)]}}
        client.get_bytes.side_effect=OSError('temporary')
        result=load_preview(client,'a.gcode')
        self.assertIsNone(result.jpeg);self.assertTrue(result.retryable)
        self.assertEqual(client.get_bytes.call_count,MAX_CANDIDATES)
