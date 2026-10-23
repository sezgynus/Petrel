from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from nfc_settings import (NFCSettings, PROFILES, available_ports, installed_enabled,
                          load, save, serial_ports_from_moonraker)
from test_capabilities import display, snapshot
from lcd_resources import ICON_NFC
from test_regressions import ui

# The GPIO-isolated UI import retains its own module references.
ViewSettings = ui.PetrelDisplay._nfc_config.__globals__['NFCSettings']


class NFCSettingsTests(unittest.TestCase):
    def test_profiles_follow_libnfc_interface_families(self):
        self.assertEqual(PROFILES['PN532']['interfaces'], ('UART', 'I2C', 'SPI'))
        self.assertEqual(PROFILES['ARYGON']['interfaces'], ('UART',))
        self.assertEqual(NFCSettings('PN532', 'UART', '/dev/ttyAMA0', 115200).connection_string(),
                         'pn532_uart:/dev/ttyAMA0:115200')
        self.assertEqual(NFCSettings('PN532', 'I2C', '/dev/i2c-1', 0).connection_string(),
                         'pn532_i2c:/dev/i2c-1')
        self.assertEqual(NFCSettings('PN532', 'SPI', '/dev/spidev0.0', 0).connection_string(),
                         'pn532_spi:/dev/spidev0.0')

    def test_clock_fields_are_inactive_for_non_uart_interfaces(self):
        view = display(snapshot())
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': True}
        for interface in ('I2C', 'SPI', 'USB', 'PC/SC', 'NCI'):
            model = {'USB': 'PN53x USB', 'PC/SC': 'PC/SC reader', 'NCI': 'PN71xx'}.get(interface, 'PN532')
            view._nfc_values = ViewSettings(model, interface, '/dev/test', 0)
            self.assertFalse(view._nfc_field_enabled('speed'))
            self.assertEqual(view._nfc_options('speed'), ())
            self.assertEqual(view._nfc_value_text('speed'), 'Not applicable')
        view._nfc_values = ViewSettings('PN532', 'UART', '/dev/test', 115200)
        self.assertTrue(view._nfc_field_enabled('speed'))

    def test_invalid_interfaces_ports_and_speeds_are_rejected(self):
        for value in (NFCSettings('ARYGON', 'SPI', '/dev/spidev0.0', 0),
                      NFCSettings('PN532', 'UART', '/dev/ttyAMA0', 12345),
                      NFCSettings('PN532', 'UART', '', 115200)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                value.validate()

    def test_settings_save_atomically_and_load_validated_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Petrel' / 'nfc-settings.json'
            original = NFCSettings('PN532', 'SPI', '/dev/spidev0.0', 0)
            save(original, path)
            self.assertEqual(load(path), original)
            self.assertEqual(json.loads(path.read_text())['speed'], 0)
            path.write_text('{"model":"unknown"}')
            self.assertEqual(load(path), NFCSettings())

    def test_installation_flag_controls_nfc_availability(self):
        self.assertTrue(installed_enabled({'PETREL_NFC': '1'}))
        self.assertTrue(installed_enabled({'PETREL_NFC': 'y'}))
        self.assertFalse(installed_enabled({'PETREL_NFC': '0'}))
        self.assertFalse(installed_enabled({'PETREL_NFC': 'n'}))

    def test_bus_port_lists_include_only_existing_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            dev = Path(directory)
            (dev / 'ttyAMA0').touch()
            (dev / 'ttyS0').touch()
            (dev / 'i2c-1').touch()
            (dev / 'spidev0.0').touch()
            # Even when /dev contains multiple UART nodes/aliases, Petrel
            # must never reintroduce its old filesystem-based serial list.
            self.assertEqual(available_ports('UART', 'PN532', dev), ())
            self.assertEqual(available_ports('I2C', 'PN532', dev), (str(dev / 'i2c-1'),))
            self.assertEqual(available_ports('SPI', 'PN532', dev), (str(dev / 'spidev0.0'),))

    def test_moonraker_serial_response_uses_canonical_paths_only(self):
        data = {'result': {'serial_devices': [
            {'device_type': 'hardware_uart', 'device_path': '/dev/ttyS0'},
            {'device_type': 'usb', 'device_path': '/dev/ttyUSB0',
             'path_by_id': '/dev/serial/by-id/usb-reader',
             'path_by_hardware': '/dev/serial/by-path/usb-reader'},
            {'device_type': 'hardware_uart', 'device_path': '/dev/ttyAMA0'},
            {'device_type': 'hardware_uart', 'device_path': '/dev/ttyDWIN0'},
            {'device_type': 'hardware_uart', 'device_path': '/dev/ttyDWIN0'},
            {'device_type': 'usb', 'device_path': '/dev/ttyS_DWIN0'},
            {'device_type': 'usb', 'device_path': '/dev/../etc/passwd'},
            {'device_type': 'video', 'device_path': '/dev/video0'},
            {'device_type': 'usb', 'device_path': 123},
        ]}}
        # Moonraker itself normally returns only canonical paths; duplicate
        # entries are also filtered. It does not enumerate serial0/by-path.
        data['result']['serial_devices'].pop(5)
        self.assertEqual(serial_ports_from_moonraker(data),
                         ('/dev/ttyS0', '/dev/ttyUSB0',
                          '/dev/ttyAMA0', '/dev/ttyDWIN0'))
        for response in ({}, {'result': {}}, {'result': {'serial_devices': None}},
                         {'result': []}):
            with self.subTest(response=response), self.assertRaises(ValueError):
                serial_ports_from_moonraker(response)

    def test_moonraker_backend_uses_shared_bounded_read_worker(self):
        view = display(snapshot())
        view.pd._read_worker = Mock()
        view.pd.client.get = Mock(return_value={'result': {'serial_devices': [
            {'device_type': 'hardware_uart', 'device_path': '/dev/ttyDWIN0'}]}})
        view.pd.discover_serial_ports()
        work = view.pd._read_worker.submit.call_args.args[0]
        self.assertEqual(work(), ('/dev/ttyDWIN0',))
        view.pd.client.get.assert_called_once_with('/machine/peripherals/serial')

    def test_non_uart_port_discovery_is_async_and_never_runs_during_paint(self):
        from concurrent.futures import Future
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view._nfc_values = ViewSettings('PN53x USB', 'USB', '', 0)
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': False}
        view._nfc_port_choices = None
        pending = Future()
        view.pd.discover_nfc_devices = Mock(return_value=pending)
        with patch.dict('os.environ', {'PETREL_NFC': '1'}), \
                patch('ui_nfc_settings.available_ports',
                      side_effect=AssertionError('hardware I/O on UI thread')):
            view.checkkey = view.NFCSettingsMenu
            self.assertEqual(view._nfc_options('port'), ())
            view.Draw_NFC_Settings_Menu()
            view.pd.discover_nfc_devices.assert_called_once_with('PN53x USB', 'USB')
            pending.set_result(('pn53x_usb:001:003',))
            self.assertTrue(view._nfc_poll_port_choices())
            self.assertEqual(view._nfc_options('port'), ('pn53x_usb:001:003',))
            self.assertIn(4, view._nfc_focusable())

    def test_settings_helpers_never_open_an_independent_libnfc_context(self):
        # USB/PCSC/NCI enumeration is serialized by NFCBackend.discover_devices;
        # nfc_settings must remain safe to call from any UI/settings context.
        with patch('libnfc_api.list_devices', side_effect=AssertionError(
                'libnfc accessed outside the backend')):
            for model, interface in (('PN53x USB', 'USB'),
                                     ('ACR122U', 'USB'),
                                     ('ACR122U', 'PC/SC'),
                                     ('PN71xx', 'NCI')):
                with self.subTest(model=model, interface=interface):
                    self.assertEqual(available_ports(interface, model), ())

    def test_nfc_entry_icon_and_info_style_read_only_status(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view.Draw_Display_Menu()
        rows = view._draw_list_menu.call_args.args[1]
        self.assertEqual(rows[-1][0], 'NFC settings')
        self.assertEqual(rows[-1][1], ICON_NFC)
        self.assertNotEqual(ICON_NFC, view.ICON_Info)

        with patch.dict('os.environ', {'PETREL_NFC': '1'}):
            view.Draw_NFC_Settings_Menu()
        rows = view._draw_list_menu.call_args.args[1]
        self.assertEqual(rows[1][:3], ('', None, 'Enabled'))
        self.assertEqual(view._nfc_focusable(), [0, 2])
        view._draw_menu_text = Mock()
        view.lcd.reset_mock()
        rows[1][3](1)
        view._draw_menu_text.assert_called_once_with(
            'NFC feature', view.LBLX, view.MBASE(1) - 1)
        view.lcd.draw_text.assert_called_once_with(
            False, True, view.lcd.font8x16, 0x07E0,
            view.lcd.Color_Bg_Black,
            view.MENU_VALUE_RIGHT - 8 * view.MENU_CHR_W,
            view.MBASE(1) - 1, ' Enabled')

    def test_disabled_installation_shows_rows_without_moving_focus(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        with patch.dict('os.environ', {'PETREL_NFC': '0'}):
            view.Draw_NFC_Settings_Menu()
        title, entries, selection = view._draw_list_menu.call_args.args
        self.assertEqual(selection, 0)
        self.assertEqual(entries[1][2], 'Disabled in setup')
        self.assertEqual([entry[0] for entry in entries],
                         ['Back', '', 'RFID module', 'Interface',
                          'Port / device', 'Link speed', 'Save', 'Test connection'])
        self.assertIsNone(entries[1][1])
        self.assertTrue(all(not entry[2][1] for entry in entries[2:]))
        view._draw_menu_text = Mock()
        view.lcd.reset_mock()
        entries[1][3](1)
        view._draw_menu_text.assert_called_once_with(
            'NFC feature', view.LBLX, view.MBASE(1) - 1)
        view.lcd.draw_text.assert_called_once_with(
            False, True, view.lcd.font8x16, 0x9CD3,
            view.lcd.Color_Bg_Black,
            view.MENU_VALUE_RIGHT - 8 * view.MENU_CHR_W,
            view.MBASE(1) - 1, 'Disabled')
        view._nfc_selection = 0
        view.checkkey = view.NFCSettingsMenu
        view._encoder_event = view.ENCODER_DIFF_CW
        with patch.dict('os.environ', {'PETREL_NFC': '0'}):
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 1)
            self.assertIsNone(view._draw_list_menu.call_args.args[2])
            for _ in range(6):
                view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 7)
            self.assertIsNone(view._draw_list_menu.call_args.args[2])
            self.assertEqual(view._draw_list_menu.call_args.kwargs['start'], 2)
            self.assertEqual(view._draw_list_menu.call_args.args[1][-1][0],
                             'Test connection')
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view.checkkey, view.NFCSettingsMenu)
            view._encoder_event = view.ENCODER_DIFF_CCW
            for _ in range(7):
                view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 0)
            self.assertEqual(view._draw_list_menu.call_args.args[2], 0)

    def test_child_fields_become_focusable_only_after_parent_confirmation(self):
        view = display(snapshot())
        view._nfc_values = ViewSettings()
        view._nfc_confirmed = {'model': False, 'interface': False, 'port': False}
        self.assertEqual(view._nfc_focusable(), [0, 2])
        view._nfc_confirmed['model'] = True
        self.assertEqual(view._nfc_focusable(), [0, 2, 3])

    def test_disabled_rows_scroll_one_step_without_focus_until_active_action(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        port = 'pn53x_usb:001:003'
        view._nfc_values = ViewSettings('PN53x USB', 'USB', port, 0)
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': True}
        view._nfc_port_choices = (('PN53x USB', 'USB'), (port,))
        view._nfc_selection = 4
        view.checkkey = view.NFCSettingsMenu
        view._encoder_event = view.ENCODER_DIFF_CW
        with patch.dict('os.environ', {'PETREL_NFC': '1'}):
            self.assertEqual(view._nfc_focusable(), [0, 2, 3, 4, 6, 7])
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 5)
            self.assertIsNone(view._draw_list_menu.call_args.args[2])
            # Inactive link speed must not start a selection operation.
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view.checkkey, view.NFCSettingsMenu)
            view._encoder_event = view.ENCODER_DIFF_CW
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 6)
            self.assertEqual(view._draw_list_menu.call_args.args[2], 6)
            self.assertEqual(view._draw_list_menu.call_args.kwargs['start'], 1)
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 7)
            self.assertEqual(view._draw_list_menu.call_args.args[2], 7)
            self.assertEqual(view._draw_list_menu.call_args.kwargs['start'], 2)
            view._encoder_event = view.ENCODER_DIFF_CCW
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 6)
            self.assertEqual(view._draw_list_menu.call_args.args[2], 6)
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 5)
            self.assertIsNone(view._draw_list_menu.call_args.args[2])

    def test_list_renderer_keeps_disabled_rows_cursorless_while_scrolling(self):
        view = display(snapshot())
        view.checkkey = view.NFCSettingsMenu
        view.Draw_Menu_Cursor = Mock()
        view.Erase_Menu_Cursor = Mock()
        view._nfc_values = ViewSettings()
        view._nfc_confirmed = {'model': False, 'interface': False, 'port': False}
        view._nfc_selection = 0
        view._encoder_event = view.ENCODER_DIFF_CW
        with patch.dict('os.environ', {'PETREL_NFC': '1'}):
            view.Draw_NFC_Settings_Menu()
            view.Draw_Menu_Cursor.assert_not_called()
            view.lcd.show_icon.assert_any_call(view.ICON, view.ICON_Back, 6, 5,
                                               background=False, enhanced=True)
            view.Draw_Menu_Cursor.reset_mock()
            # Skip the read-only feature status and focus the RFID model.
            view.HMI_NFC_Settings_Menu()
            view.Draw_Menu_Cursor.assert_not_called()
            view.HMI_NFC_Settings_Menu()
            view.Draw_Menu_Cursor.assert_called_once_with(1)
            view.Draw_Menu_Cursor.reset_mock()
            # All following settings are disabled; scrolling still reveals
            # the final test row, without drawing a cursor offscreen.
            for _ in range(5):
                view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 7)
            self.assertEqual(view._list_render['start'], 2)
            self.assertIsNone(view._list_render['selection'])
            view.Draw_Menu_Cursor.assert_not_called()
            view._encoder_event = view.ENCODER_DIFF_CCW
            for _ in range(5):
                view.HMI_NFC_Settings_Menu()
            self.assertEqual(view._nfc_selection, 2)
            self.assertEqual(view._list_render['selection'], 2)
            view.Draw_Menu_Cursor.assert_called_with(0)

    def test_model_choice_submenu_and_cancel_semantics(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view._nfc_values = ViewSettings()
        view._nfc_confirmed = {'model': False, 'interface': False, 'port': False}
        view._nfc_selection = 2
        view.checkkey = view.NFCSettingsMenu
        with patch.dict('os.environ', {'PETREL_NFC': '1'}):
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view.checkkey, view.NFCChoiceMenu)
            self.assertEqual(view._nfc_choice_field, 'model')
            self.assertEqual(view._draw_list_menu.call_args.args[0], 'RFID module')
            self.assertEqual(view._draw_list_menu.call_args.args[1][0][0], 'Back')

            # Back leaves the draft and parent confirmations untouched.
            view._nfc_choice_selection = 0
            view.HMI_NFC_Choice_Menu()
            self.assertEqual(view.checkkey, view.NFCSettingsMenu)
            self.assertEqual(view._nfc_values, ViewSettings())
            self.assertEqual(view._nfc_focusable(), [0, 2])

            # Choosing a reader returns to the settings summary.
            view._nfc_selection = 2
            view.HMI_NFC_Settings_Menu()
            view._nfc_choice_selection = view._nfc_choice_options.index('ACR122U') + 1
            view.HMI_NFC_Choice_Menu()
            self.assertEqual(view.checkkey, view.NFCSettingsMenu)
            self.assertEqual(view._nfc_values,
                             ViewSettings('ACR122U', 'USB', '', 0))
            self.assertEqual(view._nfc_confirmed,
                             {'model': True, 'interface': False, 'port': False})
            self.assertEqual(view._nfc_focusable(), [0, 2, 3])
            entries = view._draw_list_menu.call_args.args[1]
            self.assertEqual(entries[2][2], ('ACR122U', True))
            self.assertEqual(entries[3][2], ('Select', True))

    def test_port_and_speed_submenus_save_only_after_confirmation(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view._nfc_values = ViewSettings('PN532', 'UART', '', 115200)
        view._nfc_saved = view._nfc_values
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': False}
        view._nfc_selection = 4
        view.checkkey = view.NFCSettingsMenu
        ports = ('/dev/ttyAMA0', '/dev/ttyDWIN0')
        future = Future()
        future.set_result(ports)
        view.pd.discover_nfc_devices = Mock(return_value=future)
        fake_save = Mock()
        save_code = view.HMI_NFC_Settings_Menu.__func__.__globals__
        with patch.dict('os.environ', {'PETREL_NFC': '1'}), \
                patch.dict(save_code, {'save': fake_save}):
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view.checkkey, view.NFCChoiceMenu)
            view.pd.discover_nfc_devices.assert_called_once_with('PN532', 'UART')
            self.assertEqual(view._nfc_choice_options, ())
            self.assertEqual(view._draw_list_menu.call_args.args[1][-1][0], 'Loading...')
            self.assertTrue(view._nfc_poll_port_choices())
            self.assertEqual(view._nfc_choice_options, ports)
            view._nfc_choice_selection = 2
            view.HMI_NFC_Choice_Menu()
            self.assertEqual(view._nfc_values.port, '/dev/ttyDWIN0')
            self.assertTrue(view._nfc_confirmed['port'])
            self.assertEqual(view._nfc_value_text('port'), 'ttyDWIN0')
            self.assertEqual(view._nfc_focusable(), [0, 2, 3, 4, 5, 6, 7])

            view._nfc_selection = 5
            view.HMI_NFC_Settings_Menu()
            self.assertEqual(view.checkkey, view.NFCChoiceMenu)
            self.assertEqual(view._nfc_choice_options[-1], 921600)
            view._nfc_choice_selection = view._nfc_choice_options.index(230400) + 1
            view.HMI_NFC_Choice_Menu()
            self.assertEqual(view._nfc_values.speed, 230400)
            self.assertFalse(fake_save.called)

            rows = view._draw_list_menu.call_args.args[1]
            self.assertEqual(rows[4][2], ('ttyDWIN0', True))
            self.assertEqual(rows[5][2], ('230400', True))
            view._draw_menu_value = Mock()
            rows[4][3](4)
            view._draw_menu_value.assert_called_once_with(
                'ttyDWIN0', view.MBASE(4) - 1, view.lcd.Color_Bg_Black, 9)
            view._nfc_selection = 6
            view.HMI_NFC_Settings_Menu()
            fake_save.assert_called_once_with(view._nfc_values)
            self.assertEqual(view._nfc_saved, view._nfc_values)

    def test_save_notifies_backend_without_closing_worker_on_ui_thread(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        config = ViewSettings('PN532', 'UART', '/dev/ttyAMA0', 115200)
        view._nfc_values = config
        view._nfc_saved = ViewSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200)
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': True}
        view._nfc_selection = 6
        view.checkkey = view.NFCSettingsMenu
        view.pd.reload_nfc_configuration = Mock()
        saved = Mock()
        code = view.HMI_NFC_Settings_Menu.__func__.__globals__
        with patch.dict('os.environ', {'PETREL_NFC': '1'}), \
                patch.dict(code, {'save': saved}):
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Settings_Menu()
        saved.assert_called_once_with(config)
        view.pd.reload_nfc_configuration.assert_called_once_with()

    def test_manual_connection_test_reports_success_and_failure_without_saving(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view._nfc_values = ViewSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200)
        view._nfc_saved = view._nfc_values
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': True}
        view._nfc_selection = 7
        view.checkkey = view.NFCSettingsMenu
        future = Future()
        view.pd.test_nfc_connection = Mock(return_value=future)
        globals_ = view.HMI_NFC_Settings_Menu.__func__.__globals__
        fake_save = Mock()
        with patch.dict('os.environ', {'PETREL_NFC': '1'}), \
                patch.dict(globals_, {'save': fake_save}):
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Settings_Menu()
            view.pd.test_nfc_connection.assert_called_once_with(view._nfc_values)
            rows = view._draw_list_menu.call_args.args[1]
            self.assertEqual(rows[7][:3],
                             ('Test connection', 124, ('Wait', True)))
            self.assertEqual(rows[6][2][0], 'Busy')
            self.assertFalse(view._nfc_poll_test_connection())
            future.set_result(True)
            self.assertTrue(view._nfc_poll_test_connection())
            rows = view._draw_list_menu.call_args.args[1]
            self.assertEqual(rows[7][2], ('OK', True))
            view.lcd.reset_mock()
            rows[7][3](7)
            view.lcd.draw_text.assert_called_once_with(
                False, True, view.lcd.font8x16, 0x07E0,
                view.lcd.Color_Bg_Black,
                view.MENU_VALUE_RIGHT - 4 * view.MENU_CHR_W,
                view.MBASE(7) - 1, '  OK')
            # A connectivity test never modifies the persisted settings.
            fake_save.assert_not_called()
            self.assertEqual(view._nfc_saved, view._nfc_values)
            second = Future()
            second.set_exception(OSError('device not found'))
            view.pd.test_nfc_connection.return_value = second
            view.HMI_NFC_Settings_Menu()
            self.assertTrue(view._nfc_poll_test_connection())
            rows = view._draw_list_menu.call_args.args[1]
            self.assertEqual(rows[7][2], ('Fail', True))
            view.lcd.reset_mock()
            rows[7][3](7)
            view.lcd.draw_text.assert_called_once_with(
                False, True, view.lcd.font8x16, 0xF800,
                view.lcd.Color_Bg_Black,
                view.MENU_VALUE_RIGHT - 4 * view.MENU_CHR_W,
                view.MBASE(7) - 1, 'Fail')

    def test_connection_test_disabled_until_valid_configuration(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view._nfc_values = ViewSettings()
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': False}
        with patch.dict('os.environ', {'PETREL_NFC': '1'}):
            view.Draw_NFC_Settings_Menu()
            self.assertNotIn(7, view._nfc_focusable())
            self.assertEqual(view._draw_list_menu.call_args.args[1][7][2],
                             ('Run', False))
            view._nfc_values = ViewSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200)
            view._nfc_confirmed['port'] = True
            view.Draw_NFC_Settings_Menu()
            self.assertIn(7, view._nfc_focusable())

    def test_uart_port_discovery_error_and_retry_after_cancel(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view._nfc_values = ViewSettings()
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': False}
        view._nfc_selection = 4
        view.checkkey = view.NFCSettingsMenu
        pending = Future()
        second = Future()
        view.pd.discover_nfc_devices = Mock(side_effect=[pending, second])
        with patch.dict('os.environ', {'PETREL_NFC': '1'}):
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Settings_Menu()
            self.assertIs(view._nfc_port_future, pending)
            view._encoder_event = view.ENCODER_DIFF_CW
            view.HMI_NFC_Choice_Menu()
            # Loading placeholder is never focusable.
            self.assertEqual(view.checkkey, view.NFCChoiceMenu)
            self.assertEqual(view._nfc_choice_selection, 0)
            view._encoder_event = view.ENCODER_DIFF_ENTER
            view.HMI_NFC_Choice_Menu()
            self.assertEqual(view.checkkey, view.NFCSettingsMenu)
            self.assertTrue(pending.cancelled())
            view.HMI_NFC_Settings_Menu()
            self.assertIs(view._nfc_port_future, second)
            second.set_exception(ValueError('Moonraker unavailable'))
            self.assertTrue(view._nfc_poll_port_choices())
            self.assertEqual(view._nfc_choice_options, ())
            self.assertEqual(view._draw_list_menu.call_args.args[1][-1][0], 'Unavailable')
            self.assertIn(4, view._nfc_focusable())

    def test_choice_rendering_truncates_long_ports_and_shows_checkmark(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        view._nfc_values = ViewSettings('PN532', 'UART', '/dev/ttyDWIN0', 115200)
        view._nfc_confirmed = {'model': True, 'interface': True, 'port': True}
        view._nfc_choice_field = 'port'
        view._nfc_choice_options = ('/dev/serial/by-id/very-long-usb-adapter-name',
                                    '/dev/ttyDWIN0')
        view._nfc_choice_selection = 2
        view.Draw_NFC_Choice_Menu()
        title, entries, selection = view._draw_list_menu.call_args.args
        self.assertEqual((title, selection), ('Port / device', 2))
        self.assertTrue(all(len(entry[0]) <= 22 for entry in entries))
        self.assertEqual([row[2] for row in entries], [None, False, True])
        self.assertIn('adapter-name', entries[1][0])


if __name__ == '__main__':
    unittest.main()

