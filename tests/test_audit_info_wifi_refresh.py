import unittest
from unittest.mock import Mock
from test_regressions import ui

class InfoWifiRefresh(unittest.TestCase):
    def test_wifi_only_change_refreshes_info_and_unchanged_tick_does_not(self):
        v=ui.PetrelDisplay.__new__(ui.PetrelDisplay)
        v.pd=Mock();v.lcd=Mock();v.checkkey=v.Info;v._offline=False
        v.pd.connection_error=v.pd.last_command_error=None
        v.last_status=v.pd.status='standby'
        v.pd.HMI_flag.home_flag=False
        v.pd.refresh_wifi_status=Mock(side_effect=[True,False])
        v.pd.refresh_system_info=Mock(return_value=False)
        v.pd.refresh_nfc_info=Mock(return_value=False)
        v.pd._rfid_reader=None
        for name in ('_poll_case_light_live','_sync_case_light_tracking','_poll_case_light_state',
                     '_poll_maintenance_ui','_focus_tick_quiet','_poll_screws_tilt','_poll_bed_mesh',
                     'Draw_Info_Menu','Draw_Status_Area'):
            setattr(v,name,Mock())
        for name in ('_update_ui_state','_poll_recovery_ui','_configure_menus','_poll_action','_poll_print_start'):
            setattr(v,name,Mock(return_value=False))
        v._poll_mmu=Mock()
        v._software_updater=Mock(return_value=Mock(poll=Mock(return_value=False)))
        v._each_moment_update_untraced()
        v.Draw_Info_Menu.assert_called_once()
        v._each_moment_update_untraced()
        v.Draw_Info_Menu.assert_called_once()
        self.assertEqual(v.pd.refresh_wifi_status.call_count,2)
