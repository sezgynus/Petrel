"""CI-only recovery dirty regions, negative cache and installed version checks."""
from concurrent.futures import Future
from dataclasses import replace
from unittest.mock import Mock, patch
import unittest
from test_recovery_ui import RecoveryUITests
from test_thumbnail_preview import png
from thumbnail_preview import load_preview, load_thumbnail, MAX_CANDIDATES
from thumbnail_cache import ThumbnailCache
from preview_metadata import PreviewData, PreviewDetails
from petrel_version import client_version

class AuditPresentationTests(unittest.TestCase):
    def test_recovery_focus_only_repaints_old_and_new_buttons(self):
        fixture=RecoveryUITests();v=fixture.view();fixture.enter(v)
        v.Clear_Popup_Area=Mock();v.lcd.reset_mock()
        v._process_input(fixture.event(v,'rotate',1))
        v.Clear_Popup_Area.assert_not_called()
        texts=[c.args[-1] for c in v.lcd.draw_text.call_args_list]
        self.assertEqual(set(texts),{'Firmware Restart','Refresh connection'})
        self.assertEqual(v.lcd.draw_rectangle.call_count,4)

    def test_shortened_error_and_cleared_notice_erase_only_changed_regions(self):
        fixture=RecoveryUITests();v=fixture.view();fixture.enter(v)
        v.pd.recovery.notice='Pending';v.Draw_Recovery()
        v.Clear_Popup_Area=Mock();v.lcd.reset_mock()
        v.pd.recovery.notice=''
        v.pd.recovery.state=replace(v.pd.recovery.state,message='short')
        v.Draw_Recovery()
        v.Clear_Popup_Area.assert_not_called()
        self.assertNotIn('Firmware Restart',[c.args[-1] for c in v.lcd.draw_text.call_args_list])
        self.assertTrue(any(c.args[-3:]==(296,259,327) for c in v.lcd.draw_rectangle.call_args_list))

    def test_positive_no_thumbnail_is_not_retried_but_new_identity_is(self):
        client=Mock();client.get.return_value={'result':{'estimated_time':123,'thumbnails':[]}}
        data=load_preview(client,'a.gcode')
        self.assertFalse(data.retryable);self.assertEqual(data.details.seconds,123)
        f=Future();f.set_result(data)
        loader=Mock(return_value=f);cache=ThumbnailCache(client,loader=loader)
        key=('a.gcode',1,100,None);cache.sync(1,[key],[key])
        lcd=Mock()
        with patch('thumbnail_cache.time.monotonic',return_value=0):cache.tick(lcd);cache.tick(lcd)
        with patch('thumbnail_cache.time.monotonic',return_value=10000):cache.tick(lcd)
        self.assertEqual(loader.call_count,1)
        replacement=('a.gcode',2,100,None);cache.sync(1,[replacement],[replacement]);cache.tick(lcd)
        self.assertEqual(loader.call_count,2)

    def test_broken_preferred_image_falls_back_and_attempts_are_bounded(self):
        client=Mock();metadata={'thumbnails':[{'relative_path':str(i)+'.png','width':128,'height':128} for i in range(10)]}
        client.get_bytes.side_effect=[b'corrupt',png()]
        self.assertTrue(load_thumbnail(client,'a.gcode',metadata).startswith(b'\xff\xd8'))
        self.assertEqual(client.get_bytes.call_count,2)
        client.get_bytes.reset_mock();client.get_bytes.side_effect=OSError('offline')
        with self.assertRaises(ValueError):load_thumbnail(client,'a.gcode',metadata)
        self.assertEqual(client.get_bytes.call_count,MAX_CANDIDATES)

    def test_version_is_cached_and_does_not_invent_release_when_git_unavailable(self):
        client_version.cache_clear();self.addCleanup(client_version.cache_clear)
        with patch('petrel_version.subprocess.run',return_value=Mock(stdout='v6.0.0-2-g1234567\n')) as run:
            self.assertEqual(client_version(),'v6.0.0-2-g1234567')
            self.assertEqual(client_version(),'v6.0.0-2-g1234567');run.assert_called_once()
        client_version.cache_clear()
        with patch('petrel_version.subprocess.run',side_effect=OSError('missing')):
            self.assertEqual(client_version(),'unknown')
