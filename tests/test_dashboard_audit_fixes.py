"""Header lifecycle, title bounds and Wi-Fi read isolation regressions."""
import unittest
from concurrent.futures import CancelledError
from unittest.mock import patch,call
from test_capabilities import display,printer,snapshot
from test_regressions import ui,backend
from petrel.features.maintenance.ui.layout import draw_maintenance
from petrel.features.maintenance.ui.experience import Screen,Choice
from petrel.artwork.resources import ICON_PROGRESS_FILL


class DashboardAuditFixes(unittest.TestCase):
    def test_wifi_worker_failures_clear_signal_and_apply_retry_backoff(self):
        errors=[backend.MoonrakerError(text) for text in
                ('Read queue is full','Read expired before execution','Read worker is closed')]+[CancelledError()]
        for error in errors:
            with self.subTest(error=str(error)):
                p=printer(snapshot())
                p.system_info.update(wifi_ssid='Workshop',wifi_rssi=-50)
                with patch.object(p,'_read',side_effect=error) as read,patch.object(backend.time,'monotonic',return_value=100):
                    self.assertTrue(p.refresh_wifi_status())
                    self.assertEqual((p.system_info['wifi_ssid'],p.system_info['wifi_rssi']),('Unavailable',None))
                    self.assertFalse(p.refresh_wifi_status())
                    self.assertEqual(read.call_count,1)
                    self.assertEqual(p._wifi_status_refresh_at,105)

    def test_system_info_reuses_wifi_cache_without_a_second_probe(self):
        p=printer(snapshot())
        p.system_info.update(wifi_ssid='Latest',wifi_rssi=-59)
        p.client.get.return_value={'result':{'version_info':{}}}
        with patch.object(backend,'wifi_info',side_effect=AssertionError('duplicate Wi-Fi read')) as probe:
            p.refresh_system_info(force=True)
        probe.assert_not_called()
        self.assertEqual((p.system_info['wifi_ssid'],p.system_info['wifi_rssi']),('Latest',-59))

    @patch.object(ui.time,'strftime',return_value='12:34')
    def test_maintenance_frame_clear_restores_header_indicators_on_every_page(self,clock):
        v=display(snapshot());v.pd.connection_error=None
        v.pd.system_info.update(wifi_ssid='Workshop',wifi_rssi=-59)
        v._maintenance_init()
        v.Clear_Title_Bar()
        screen=Screen('Checks',choices=(Choice('Back','back'),),kind='list')
        for page in ('groups','diagnostics','groups'):
            v._maintenance_page=page
            v.lcd.reset_mock()
            draw_maintenance(v,screen)
            self.assertIn(call(1,v.lcd.Color_Bg_Blue,259,10,266,17),v.lcd.draw_rectangle.call_args_list)
            self.assertTrue(any(c.args[1:4]==(ICON_PROGRESS_FILL,259,10) for c in v.lcd.show_icon.call_args_list))
            self.assertTrue(any(c.args[-2:]==(193,4) for c in v.lcd.show_icon.call_args_list))
            v.lcd.reset_mock()
            draw_maintenance(v,screen)
            self.assertFalse(any(c.args[-4:]==(259,10,266,17) for c in v.lcd.draw_rectangle.call_args_list))
            self.assertFalse(any(c.args[1] == ICON_PROGRESS_FILL for c in v.lcd.show_icon.call_args_list))
            self.assertFalse(any(c.args[-2:]==(193,4) for c in v.lcd.show_icon.call_args_list))

    def test_titles_always_reserve_the_wifi_region(self):
        v=display(snapshot())
        for title in ('Prepare','Mesh: '+'long-profile-'*6,'X'*24,'X'*23):
            for ssid in ('Workshop','Disconnected'):
                v.pd.system_info.update(wifi_ssid=ssid,wifi_rssi=-59)
                v.lcd.reset_mock()
                v.Draw_Title(title)
                args=next(c.args for c in v.lcd.draw_text.call_args_list if c.args[5]==14)
                self.assertLessEqual(14+len(args[-1])*8,190)
                if len(title)>22:self.assertTrue(args[-1].endswith('...'))
                else:self.assertEqual(args[-1],title)
