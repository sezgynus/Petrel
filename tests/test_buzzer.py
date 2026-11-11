from test_regressions import startup
from pathlib import Path
from concurrent.futures import Future
from threading import Event
import struct
import tempfile
import time
from unittest.mock import Mock, patch, call
import unittest
import zlib

from petrel.features.buzzer.control import Player, ADDRESS, RECORD_SIZE, LEGACY_RECORD_SIZE
from petrel.features.buzzer.pwm import HardwarePWM, PWM_PINS
from test_capabilities import snapshot, display
from test_regressions import ui
from test_t5uic1_driver import driver
# The UI fixture imports a separate mocked module instance in isolation.
Settings = ui.BuzzerSettings


class BuzzerSettingsTests(unittest.TestCase):
    def test_new_record_roundtrip_and_corruption(self):
        value = Settings(False, 80, 5, 0)
        raw = value.encode()
        self.assertEqual(len(raw), RECORD_SIZE)
        self.assertEqual(raw[:8], b'PETBZR02')
        self.assertEqual(Settings.decode(raw), value)
        broken = bytearray(raw)
        broken[15] ^= 1
        self.assertIsNone(Settings.decode(broken))
        self.assertIsNone(Settings.decode(bytes(RECORD_SIZE)))
        for invalid in (Settings(enabled=1), Settings(volume=101), Settings(click=9)):
            with self.assertRaises(ValueError):
                invalid.encode()

    def test_import_legacy_klipper_choice_as_enabled_state_only(self):
        for name in ('Buzzer', ''):
            body = struct.pack('>8sBBB', b'PETBZR01', 70, 4, 1)
            body += name.encode() + b'\0'
            body = body.ljust(LEGACY_RECORD_SIZE - 4, b'\0')
            raw = body + struct.pack('>I', zlib.crc32(body))
            expected = Settings(bool(name), 70, 4, 1)
            self.assertEqual(Settings.decode(raw), expected)
            self.assertEqual(Settings.decode(raw[:RECORD_SIZE]), expected)
            self.assertEqual(Settings.decode(raw).encode()[:8], b'PETBZR02')

    def test_migrate_old_128_byte_record_through_16_byte_panel_read(self):
        for enabled in (False, True):
            chosen = Settings(enabled, 100, 5, 4)
            body = struct.pack('>8sBBBB', b'PETBZR02', chosen.volume,
                               chosen.click, chosen.encoder, int(chosen.enabled))
            body = body.ljust(LEGACY_RECORD_SIZE - 4, b'\0')
            legacy = body + struct.pack('>I', zlib.crc32(body))
            self.assertEqual(Settings.decode(legacy), chosen)
            self.assertEqual(Settings.decode(legacy[:RECORD_SIZE]), chosen)
            upgraded = Settings.decode(legacy[:RECORD_SIZE]).encode()
            self.assertEqual(len(upgraded), 16)
            self.assertEqual(Settings.decode(upgraded), chosen)
        # New records must have a valid checksum; a damaged CRC is not
        # mistaken for the legacy padded format.
        corrupted = bytearray(chosen.encode())
        corrupted[-1] ^= 0x40
        self.assertIsNone(Settings.decode(corrupted))


    def test_flash_record_verification(self):
        lcd = driver()
        value = Settings(True, 10, 3, 4)
        lcd.write_flash = Mock()
        lcd.read_flash = Mock(return_value=value.encode())
        lcd.save_buzzer_settings(value)
        lcd.write_flash.assert_called_once_with(ADDRESS, value.encode())
        self.assertEqual(lcd.load_buzzer_settings().encode(), value.encode())
        lcd.read_flash.return_value = bytes(RECORD_SIZE)
        with self.assertRaises(OSError):
            lcd.save_buzzer_settings(value)


class BuzzerMenuTests(unittest.TestCase):
    def view(self):
        view = display(snapshot())
        view._display_values = [100, 0, 10]
        view._display_saved = (100, 0, 10)
        view._display_selection = 4
        view._buzzer_values = view._buzzer_saved = Settings()
        view.checkkey = view.DisplayMenu
        view.get_encoder_state = Mock()
        return view

    def step(self, view, event):
        view.get_encoder_state.return_value = event
        view.HMI_Display_Menu()

    def test_toggle_in_display_saves_without_klipper_output_selector(self):
        view = self.view()
        self.assertEqual([r[0] for r in view._buzzer_rows()],
                         ['Buzzer', 'Volume', 'Click tone', 'Encoder tone'])
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertFalse(view._buzzer_values.enabled)
        self.assertEqual(view.checkkey, view.DisplayMenu)
        self.assertEqual(len(view._buzzer_rows()), 4)
        view.lcd.save_buzzer_settings.assert_called_once_with(Settings(False))
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertTrue(view._buzzer_values.enabled)

    def test_saved_preferences_survive_uart_reconnect(self):
        from test_uart_reconnect import UARTReconnectTests
        view = UARTReconnectTests().display()
        saved = Settings(False, 70, 4, 1)
        view.lcd.load_buzzer_settings.return_value = saved
        with patch.object(startup, 'T5UIC1Display', return_value=view.lcd):
            self.assertTrue(view._ensure_uart())
            self.assertEqual(view._buzzer_settings(), saved)
            view._uart_online = False
            self.assertTrue(view._ensure_uart())
        view.lcd.load_buzzer_settings.assert_called_once_with()

    def test_buzzer_rows_share_display_fixed_width_and_vertical_baseline(self):
        view = self.view()
        view._buzzer_values = Settings(False, 100, 5, 4)
        view.Draw_Display_Menu()
        values = [call.args for call in view.lcd.draw_text.call_args_list]
        buzzer = next(args for args in values if args[-1] == '  Disabled')
        volume = next(args for args in values if args[-1] == '      100%')
        brightness = next(args for args in values if args[-1] == '   100%')
        for args in (buzzer, volume):
            self.assertEqual(args[0:2], (False, True))
            self.assertEqual(args[-3], view.MENU_VALUE_RIGHT - 10 * 8)
            self.assertEqual(args[-3] + 10 * 8, view.MENU_VALUE_RIGHT)
        self.assertEqual(brightness[-3] + 7 * 8, view.MENU_VALUE_RIGHT)
        # Label and value use identical row y, not independent baselines.
        line = next(args for args in values if args[-1] == 'Buzzer')
        self.assertEqual(buzzer[-2], line[-2])
        view._list_render = None
        view._display_selection = 6
        view.Draw_Display_Menu()
        tone = next(c.args for c in view.lcd.draw_text.call_args_list
                    if c.args[-1] == '    Double')
        self.assertEqual(tone[-3] + 10 * 8, view.MENU_VALUE_RIGHT)

    def test_buzzer_row_uses_enabled_disabled_labels(self):
        view = self.view()
        self.assertEqual(view._buzzer_rows()[0], ('Buzzer', 'Enabled', True))
        view._buzzer_values = Settings(False)
        self.assertEqual(view._buzzer_rows()[0], ('Buzzer', 'Disabled', True))
        view.Draw_Display_Menu()
        labels = [c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertTrue(any(text.strip() == 'Disabled' for text in labels))

    def test_async_toggle_waits_for_verified_flash_and_survives_reload(self):
        view = self.view()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = True
        view.lcd.BUZZER_SETTINGS_ADDRESS = ADDRESS
        future = Future()
        view.lcd.begin_flash_write_verified.return_value = future
        with patch.object(view, '_draw_list_menu', wraps=view._draw_list_menu) as menu:
            self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(menu.call_args.args[0], 'Device - saving...')
        self.assertFalse(view._buzzer_values.enabled)
        self.assertTrue(view._buzzer_saved.enabled)
        self.assertEqual(view._display_save_message, 'Saving...')
        self.assertEqual(view._buzzer_rows()[0][1], 'Disabled')
        # A second press while the panel is still writing cannot overwrite it.
        self.step(view, view.ENCODER_DIFF_ENTER)
        view.lcd.begin_flash_write_verified.assert_called_once_with(
            ADDRESS, Settings(False).encode())
        future.set_result(Settings(False).encode())
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_saved, Settings(False))
        self.assertEqual(view._display_save_message, '')
        self.assertFalse(view._buzzer_save_error)
        # A fresh panel Flash load returns that same disabled value.
        view._buzzer_values = view._buzzer_saved = Settings()
        loaded = Future()
        loaded.set_result(Settings(False).encode())
        view._buzzer_load_future = loaded
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_settings(), Settings(False))
        self.assertEqual(view._buzzer_rows()[0][1], 'Disabled')

    def test_failed_async_toggle_rolls_back_and_can_retry(self):
        view = self.view()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = True
        view.lcd.BUZZER_SETTINGS_ADDRESS = ADDRESS
        failed = Future()
        view.lcd.begin_flash_write_verified.return_value = failed
        self.step(view, view.ENCODER_DIFF_ENTER)
        failed.set_exception(OSError('panel Flash did not acknowledge'))
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_values, Settings())
        self.assertEqual(view._buzzer_saved, Settings())
        self.assertTrue(view._buzzer_save_error)
        self.assertEqual(view._display_save_message, 'Not saved. Press to retry')
        self.assertEqual(view._buzzer_rows()[0][1], 'Enabled')

        saved = Future()
        view.lcd.begin_flash_write_verified.return_value = saved
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view._display_save_message, 'Saving...')
        saved.set_result(Settings(False).encode())
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_saved, Settings(False))
        self.assertFalse(view._buzzer_save_error)

    def test_async_volume_editor_waits_for_verified_flash(self):
        view = self.view()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = True
        view.lcd.BUZZER_SETTINGS_ADDRESS = ADDRESS
        view._display_selection = 5
        view._display_edit = False
        future = Future()
        view.lcd.begin_flash_write_verified.return_value = future
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.step(view, view.ENCODER_DIFF_CW)
        self.step(view, view.ENCODER_DIFF_ENTER)
        wanted = Settings(True, 60, 2, 1)
        self.assertEqual(view._buzzer_values, wanted)
        self.assertEqual(view._buzzer_saved, Settings())
        self.assertTrue(view._display_edit)
        self.assertEqual(view._display_save_message, 'Saving...')
        future.set_result(wanted.encode())
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_saved, wanted)
        self.assertFalse(view._display_edit)
        self.assertEqual(view._display_save_message, '')

    def test_volume_flash_failure_exits_edit_mode_and_user_can_retry(self):
        view = self.view()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = True
        view.lcd.BUZZER_SETTINGS_ADDRESS = ADDRESS
        view._display_selection = 5
        failed = Future()
        view.lcd.begin_flash_write_verified.return_value = failed
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.step(view, view.ENCODER_DIFF_CW)
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertTrue(view._display_edit)
        failed.set_exception(TimeoutError('DWIN Flash ACK timed out'))
        view._poll_panel_flash()
        self.assertFalse(view._display_edit)
        self.assertEqual(view._buzzer_values, Settings())
        self.assertEqual(view._buzzer_saved, Settings())
        self.assertIn('Not saved', view._display_save_message)

        # The former bug held the encoder in an editor, preventing navigation.
        self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._display_selection, 6)
        self.step(view, view.ENCODER_DIFF_CCW)
        self.assertEqual(view._display_selection, 5)
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertTrue(view._display_edit)

        self.step(view, view.ENCODER_DIFF_CW)
        succeeded = Future()
        view.lcd.begin_flash_write_verified.return_value = succeeded
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertTrue(view._display_edit)
        succeeded.set_result(Settings(True, 60, 2, 1).encode())
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_saved, Settings(True, 60, 2, 1))
        self.assertFalse(view._display_edit)

    def test_wrong_flash_readback_never_commits_toggle(self):
        view = self.view()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = True
        view.lcd.BUZZER_SETTINGS_ADDRESS = ADDRESS
        future = Future()
        view.lcd.begin_flash_write_verified.return_value = future
        self.step(view, view.ENCODER_DIFF_ENTER)
        future.set_result(Settings(True).encode())
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_saved, Settings())
        self.assertEqual(view._buzzer_values, Settings())
        self.assertTrue(view._buzzer_save_error)

    def test_verified_async_save(self):
        view = self.view()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = True
        view.lcd.BUZZER_SETTINGS_ADDRESS = ADDRESS
        future = Future()
        view.lcd.begin_flash_write_verified.return_value = future
        chosen = Settings(False, 70, 4, 1)
        view._save_buzzer(chosen)
        view.lcd.begin_flash_write_verified.assert_called_once_with(ADDRESS, chosen.encode())
        self.assertNotEqual(view._buzzer_saved, chosen)
        view._poll_panel_flash()
        self.assertNotEqual(view._buzzer_saved, chosen)
        future.set_result(chosen.encode())
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_saved, chosen)

    def test_volume_and_click_tone_persist_while_buzzer_off(self):
        view = self.view()
        view._buzzer_values = view._buzzer_saved = Settings(False)
        view._display_selection = 5
        self.step(view, view.ENCODER_DIFF_ENTER)
        for _ in range(20):
            self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._buzzer_values.volume, 100)
        view.lcd.save_buzzer_settings.assert_not_called()
        self.step(view, view.ENCODER_DIFF_ENTER)
        view.lcd.save_buzzer_settings.assert_called_once_with(Settings(False, 100))
        view._display_selection = 6
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._buzzer_values.click, 3)
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view._buzzer_saved.click, 3)

    def test_feedback_uses_pwm_worker_and_card_override(self):
        view = self.view()
        view._buzzer_player = Mock()
        view._buzzer_feedback('press')
        view._buzzer_player.play.assert_called_once_with(Settings(), 'press')
        view._buzzer_player.reset_mock()
        view._buzzer_values = Settings(False)
        view._buzzer_feedback('press')
        view._rfid_buzzer_feedback()
        view._buzzer_player.play.assert_not_called()
        view._buzzer_values = Settings(True)
        view._rfid_buzzer_feedback()
        view._buzzer_player.play_melody.assert_called_once_with(
            'NFC_TAG_READ', Settings(True), priority=True)
        view._buzzer_player.reset_mock()
        view._buzzer_values = Settings(True, volume=0, click=0, encoder=0)
        view._emergency_buzzer_feedback()
        view._buzzer_player.play_emergency.assert_called_once_with()
        view._buzzer_player.reset_mock()
        view._buzzer_values = Settings(False)
        view._emergency_buzzer_feedback()
        view._buzzer_player.play_emergency.assert_not_called()

    def test_input_plays_once_per_physical_event_and_never_for_stale_event(self):
        from petrel.ui.events import InputEvent
        view = self.view()
        view._buzzer_player = Mock()
        view._closed = False
        view._uart_epoch = 1
        view._uart_online = True
        view._sync_input_state = Mock(return_value=True)
        view._dispatch_input = Mock()
        view._display_activity = Mock(return_value=False)
        view._encoder_acceleration_cap = Mock(return_value=1)
        view._process_input(InputEvent('rotate', 7, 1, 1))
        view._buzzer_player.play.assert_called_once_with(Settings(), 'rotate')
        view._buzzer_player.reset_mock()
        view._process_input(InputEvent('press', 1, 999, 1))
        view._buzzer_player.play.assert_not_called()


class HardwarePWMTests(unittest.TestCase):
    def test_supported_pins_and_sysfs_direct_duty(self):
        self.assertEqual(PWM_PINS, {12:(0,4), 13:(1,4), 18:(0,2), 19:(1,2)})
        with tempfile.TemporaryDirectory() as tmp:
            chip = Path(tmp) / 'pwmchip0'
            path = chip / 'pwm1'
            path.mkdir(parents=True)
            (chip / 'npwm').write_text('2')
            for attr in ('enable', 'duty_cycle', 'period'):
                (path / attr).write_text('0')
            pwm = HardwarePWM(19, root=Path(tmp))
            pwm.tone(100, 100)
            self.assertEqual((path / 'period').read_text(), '10000000')
            self.assertEqual((path / 'duty_cycle').read_text(), '5000000')
            pwm.tone(100, 10)
            self.assertEqual((path / 'duty_cycle').read_text(), '500000')
            pwm.off()
            self.assertEqual((path / 'enable').read_text(), '0')
            self.assertEqual((path / 'duty_cycle').read_text(), '0')


class SoundWorkerTests(unittest.TestCase):
    def test_no_moonraker_or_klipper_dependency_and_bounded_worker(self):
        sent, off = Event(), Event()
        pwm = Mock()
        pwm.tone.side_effect = lambda *a: sent.set()
        pwm.off.side_effect = lambda: off.set()
        moonraker = Mock()
        with patch('petrel.features.buzzer.control.PATTERNS', ((), (), ((1000, 10),))):
            player = Player(moonraker, driver_factory=lambda: pwm)
            try:
                self.assertTrue(player.play(Settings(), 'press'))
                self.assertTrue(sent.wait(1))
                for _ in range(20):
                    self.assertFalse(player.play(Settings(), 'rotate'))
                player.cancel()
                self.assertTrue(off.wait(1))
            finally:
                player.close()
        pwm.tone.assert_called_once_with(1000, 50)
        moonraker.notify_immediate.assert_not_called()
        moonraker.snapshot.assert_not_called()

    def test_emergency_preempts_busy_click_at_full_power_without_rpc(self):
        pwm = Mock()
        click_started, alert_started = Event(), Event()
        def tone(frequency, volume):
            if frequency == 800:
                click_started.set()
            if frequency == 1000:
                alert_started.set()
        pwm.tone.side_effect = tone
        moonraker = Mock()
        with patch('petrel.features.buzzer.control.PATTERNS', ((), (), ((800, 10),))), \
             patch('petrel.features.buzzer.control.EMERGENCY_PATTERN',
                   ((2200, .001), (0, .001), (1000, .001))):
            player = Player(moonraker, driver_factory=lambda: pwm)
            try:
                self.assertTrue(player.play(Settings(), 'press'))
                self.assertTrue(click_started.wait(1))
                self.assertTrue(player.play_emergency())
                self.assertTrue(alert_started.wait(1), 'Alert must preempt busy clicks')
            finally:
                player.close()
        self.assertEqual(pwm.tone.call_args_list[:3],
                         [call(800, 50), call(2200, 100), call(1000, 100)])
        self.assertGreaterEqual(pwm.off.call_count, 2)
        moonraker.notify_immediate.assert_not_called()
        moonraker.request.assert_not_called()

    def test_emergency_rejected_after_player_closed(self):
        pwm = Mock()
        player = Player(driver_factory=lambda: pwm)
        player.close()
        self.assertFalse(player.play_emergency())
        pwm.tone.assert_not_called()

    def test_disabled_muted_or_off_tone_does_not_play(self):
        pwm = Mock()
        player = Player(driver_factory=lambda: pwm)
        try:
            for setting in (Settings(False), Settings(volume=0), Settings(click=0)):
                self.assertFalse(player.play(setting, 'press'))
        finally:
            player.close()
        pwm.tone.assert_not_called()


if __name__ == '__main__':
    unittest.main()
