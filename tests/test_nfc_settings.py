import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from nfc_settings import (NFCSettings, PROFILES, available_ports, installed_enabled,
                          load, save)
from test_capabilities import display, snapshot
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
            self.assertEqual(available_ports('UART', 'PN532', dev),
                             (str(dev / 'ttyAMA0'), str(dev / 'ttyS0')))
            self.assertEqual(available_ports('I2C', 'PN532', dev), (str(dev / 'i2c-1'),))
            self.assertEqual(available_ports('SPI', 'PN532', dev), (str(dev / 'spidev0.0'),))

    def test_usb_devices_are_filtered_by_selected_libnfc_driver(self):
        with patch('libnfc_api.list_devices', return_value=(
                'pn53x_usb:001:003', 'acr122_usb:001:005', 'pn532_uart:/dev/ttyUSB0:115200')):
            self.assertEqual(available_ports('USB', 'PN53x USB'), ('pn53x_usb:001:003',))
            self.assertEqual(available_ports('USB', 'ACR122U'), ('acr122_usb:001:005',))

    def test_disabled_installation_shows_rows_without_moving_focus(self):
        view = display(snapshot())
        view._draw_list_menu = Mock()
        with patch.dict('os.environ', {'PETREL_NFC': '0'}):
            view.Draw_NFC_Settings_Menu()
        title, entries, selection = view._draw_list_menu.call_args.args
        self.assertEqual(selection, 0)
        self.assertEqual(entries[1][2], 'Disabled in setup')
        self.assertTrue(all('(disabled)' in entry[0] for entry in entries[1:]))

    def test_child_fields_become_focusable_only_after_parent_confirmation(self):
        view = display(snapshot())
        view._nfc_values = ViewSettings()
        view._nfc_confirmed = {'model': False, 'interface': False, 'port': False}
        self.assertEqual(view._nfc_focusable(), [0, 2])
        view._nfc_confirmed['model'] = True
        self.assertEqual(view._nfc_focusable(), [0, 2, 3])


if __name__ == '__main__':
    unittest.main()
