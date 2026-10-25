"""Manual recovery is opt-in and cannot open the UART while the UI is active."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import reload_icons


class ReloadIconsTests(unittest.TestCase):
    def invoke(self, arguments, state='inactive', failure=None):
        lcd = Mock()
        with patch('sys.argv', ['reload_icons.py', '--serial-port', '/dev/example', *arguments]), \
                patch.object(reload_icons.subprocess, 'run', return_value=SimpleNamespace(stdout=state)), \
                patch.object(reload_icons, 'ManualDisplay', return_value=lcd) as display, \
                patch.object(reload_icons, 'sync_boot_artwork', side_effect=failure) as boot, \
                patch.object(reload_icons, 'sync_library') as icons, \
                patch.object(reload_icons, 'sync_shared_artwork') as shared:
            if state == 'active':
                with self.assertRaises(SystemExit):
                    reload_icons.main()
                display.assert_not_called()
                return
            if failure:
                with self.assertRaises(type(failure)):
                    reload_icons.main()
                icons.assert_not_called()
                shared.assert_not_called()
            else:
                reload_icons.main()
                icons.assert_called_once_with(lcd, force=True, automatic=False)
                shared.assert_called_once_with(lcd, force=True)
            lcd.close.assert_called_once()
            return lcd, boot

    def test_existing_command_does_not_force_boot(self):
        lcd, boot = self.invoke([])
        boot.assert_not_called()
        lcd.set_animation_mask.assert_called_once_with(0)

    def test_boot_option_forces_boot(self):
        lcd, boot = self.invoke(['--boot'])
        boot.assert_called_once_with(lcd, force=True)

    def test_failed_boot_repair_closes_transport_without_continuing(self):
        self.invoke(['--boot'], failure=OSError('ACK failed'))

    def test_running_ui_blocks_all_manual_repair(self):
        self.invoke(['--boot'], state='active')
