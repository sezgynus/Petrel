"""Stable checkbox bits, verified persistence and all named sound gates."""
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock
from petrel.features.buzzer.event_settings import ADDRESS, RECORD_SIZE, EVENTS, BITS, EventSounds
from test_capabilities import display, snapshot


class EventSoundRecordTests(TestCase):
    def test_all_enabled_default_independent_bits_and_crc_roundtrip(self):
        values = EventSounds()
        self.assertEqual(len(EVENTS),18)
        self.assertTrue(all(values.enabled(name) for name,_ in EVENTS))
        for name,_ in EVENTS:
            one = values.toggled(name)
            self.assertFalse(one.enabled(name))
            self.assertTrue(all(one.enabled(other) for other,_ in EVENTS if other != name))
            self.assertEqual(EventSounds.decode(one.encode()),one)
            self.assertEqual(one.toggled(name),values)
        raw = values.encode()
        self.assertEqual(len(raw),16)
        for index in range(16):
            damaged = bytearray(raw); damaged[index] ^= 1
            self.assertIsNone(EventSounds.decode(damaged))
        for missing in (b'',b'\0'*16,b'\xff'*16):
            self.assertIsNone(EventSounds.decode(missing))
        future = EventSounds(1<<31)
        self.assertEqual(EventSounds.decode(future.toggled('BOOT').encode()).disabled,(1<<31)|BITS['BOOT'])

    def test_new_hold_bit_preserves_old_choices_and_defaults_on_for_old_records(self):
        old = EventSounds((1 << 17) - 1)
        restored = EventSounds.decode(old.encode())
        self.assertTrue(restored.enabled('POWER_HOLD'))
        self.assertEqual(BITS['EMERGENCY'], 1 << 16)
        self.assertEqual(BITS['POWER_HOLD'], 1 << 17)
        muted = restored.toggled('POWER_HOLD')
        for cue in ('POWER_HOLD_START', 'POWER_HOLD_STEP', 'POWER_HOLD_READY', 'POWER_HOLD_CANCEL'):
            self.assertFalse(muted.enabled(cue))
        self.assertEqual(muted.disabled & ((1 << 17) - 1), old.disabled)
        self.assertEqual(EventSounds.decode(muted.encode()), muted)

    def test_flash_record_is_disjoint_from_all_existing_settings(self):
        from petrel.features.buzzer.control import ADDRESS as old, LEGACY_RECORD_SIZE
        from petrel.artwork.icon_library import METADATA_ADDRESS, METADATA_SIZE
        self.assertGreaterEqual(ADDRESS,old+LEGACY_RECORD_SIZE)
        self.assertGreaterEqual(ADDRESS,METADATA_ADDRESS+METADATA_SIZE)
        self.assertEqual(RECORD_SIZE,16)


class EventSoundUITests(TestCase):
    def make(self):
        view=display(snapshot())
        view._closed=False
        view._uart_online=True
        view._boot_active=False
        view._buzzer_load_complete=True
        view._sound_event_prefs_ready=True
        view._event_buzzer_ready=True
        view._event_sound_values=view._event_sound_saved=view._event_sound_settings()
        view._event_sound_selection=0
        view.checkkey=view.EventSoundsMenu
        view._buzzer_player=Mock()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH=True
        view._panel_flash_lcd=view.lcd
        view.get_encoder_state=Mock(return_value=view.ENCODER_DIFF_ENTER)
        return view

    def test_display_entry_checkboxes_initial_back_and_return_focus(self):
        view=self.make();view._draw_list_menu=Mock()
        view.Draw_Display_Menu()
        rows=view._draw_list_menu.call_args.args[1]
        self.assertEqual([r[0] for r in rows][-2:],['Event sounds','NFC settings'])
        view._display_selection=8;view._display_edit=False
        view.HMI_Display_Menu()
        self.assertEqual(view.checkkey,view.EventSoundsMenu)
        self.assertEqual(view._event_sound_selection,0)
        rows=view._draw_list_menu.call_args.args[1]
        self.assertEqual(len(rows),19)
        self.assertEqual(rows[0][0],'Back')
        self.assertTrue(all(r[2] and getattr(r[3],'checkbox',False) for r in rows[1:]))
        view.HMI_Event_Sounds_Menu()
        self.assertEqual(view.checkkey,view.DisplayMenu)
        self.assertEqual(view._display_selection,8)

    def test_async_toggle_only_commits_after_exact_readback_then_survives_restart(self):
        view=self.make();pending=Future()
        view.lcd.begin_flash_write_verified.return_value=pending
        view._event_sound_selection=1
        view.HMI_Event_Sounds_Menu()
        target=view._event_sound_save_target
        self.assertTrue(view._event_sound_enabled('BOOT'))
        self.assertFalse(target.enabled('BOOT'))
        view.lcd.begin_flash_write_verified.assert_called_once_with(ADDRESS,target.encode())
        view.HMI_Event_Sounds_Menu()
        self.assertEqual(view.lcd.begin_flash_write_verified.call_count,1)
        pending.set_result(target.encode());view._poll_panel_flash()
        self.assertFalse(view._event_sound_enabled('BOOT'))
        reboot=self.make();reboot._boot_melody_attempted=False
        reboot._adopt_event_sound_record(target.encode())
        self.assertFalse(reboot._event_sound_enabled('BOOT'))
        reboot._buzzer_player.play_melody.assert_not_called()
        self.assertTrue(reboot._boot_melody_attempted)

    def test_failed_write_rolls_back_unlocks_and_can_retry(self):
        for result in (OSError('Timeout'),b'wrong readback'):
            view=self.make();pending=Future()
            view.lcd.begin_flash_write_verified.return_value=pending
            view._event_sound_selection=2;view.HMI_Event_Sounds_Menu()
            if isinstance(result,Exception):pending.set_exception(result)
            else:pending.set_result(result)
            view._poll_panel_flash()
            self.assertTrue(view._event_sound_enabled('SHUTDOWN'))
            self.assertIsNone(view._event_sound_save_future)
            self.assertEqual(view._event_sound_message,'Not saved')
            retry=Future();view.lcd.begin_flash_write_verified.return_value=retry
            view.HMI_Event_Sounds_Menu()
            retry.set_result(view._event_sound_save_target.encode());view._poll_panel_flash()
            self.assertFalse(view._event_sound_enabled('SHUTDOWN'))

    def test_missing_record_defaults_on_and_boot_waits_for_both_loads(self):
        view=self.make();view._sound_event_prefs_ready=False
        view._event_buzzer_ready=False;view._boot_melody_attempted=False
        view._arm_buzzer_events()
        self.assertFalse(view._event_buzzer_ready)
        view._adopt_event_sound_record(b'\xff'*16)
        self.assertTrue(all(view._event_sound_enabled(n) for n,_ in EVENTS))
        view._buzzer_player.play_melody.assert_called_once()
        view=self.make();view._sound_event_prefs_ready=False
        view._buzzer_load_complete=False;view._event_buzzer_ready=False
        view._adopt_event_sound_record(b'\xff'*16)
        self.assertFalse(view._event_buzzer_ready)
        view._buzzer_load_complete=True;view._arm_buzzer_events()
        self.assertTrue(view._event_buzzer_ready)

    def test_load_failure_retries_on_press_and_pending_reconnect_restores_saved(self):
        view=self.make();view._sound_event_prefs_ready=False
        failed=Future();failed.set_exception(OSError('Read timeout'))
        view._event_sound_load_future=failed;view._poll_panel_flash()
        self.assertTrue(view._event_sound_load_failed)
        read=Future();view.lcd.begin_flash_read.return_value=read
        view._event_sound_selection=1;view.HMI_Event_Sounds_Menu()
        view.lcd.begin_flash_read.assert_called_once_with(ADDRESS,16)
        read.set_result(EventSounds().encode());view._poll_panel_flash()
        self.assertTrue(view._sound_event_prefs_ready)
        pending=Future();view.lcd.begin_flash_write_verified.return_value=pending
        view.HMI_Event_Sounds_Menu()
        view._load_event_sound_preferences(True)
        self.assertIsNone(view._event_sound_save_future)
        self.assertTrue(view._event_sound_enabled('BOOT'))

    def test_all_event_gates_and_global_mute_do_not_change_emergency_action(self):
        view=self.make()
        for name,_ in EVENTS:
            view._event_sound_values=view._event_sound_settings().toggled(name)
            view._buzzer_player.reset_mock()
            view._play_buzzer_melody(name,priority=True)
            if name=='EMERGENCY':view._emergency_buzzer_feedback()
            view._buzzer_player.play_melody.assert_not_called()
            view._buzzer_player.play_emergency.assert_not_called()
            view._event_sound_values=view._event_sound_settings().toggled(name)
        from petrel.features.nfc.core import NFCCore
        from test_nfc_core import backend
        with TemporaryDirectory() as folder:
            reader=backend();stop=Mock()
            core=NFCCore(reader,emergency_stop=stop,actions_file=Path(folder)/'actions.json')
            core.assign_global_action('emergency_stop','AA:BB')
            view._event_sound_values=view._event_sound_settings().toggled('EMERGENCY')
            view._subscribe_emergency_buzzer(core)
            reader.set_event_sink.call_args.args[0]('card.detected',{'uid':'AA:BB'})
            stop.assert_called_once()
            view._buzzer_player.play_emergency.assert_not_called()
            core.close()

    def test_master_mute_and_volume_with_enabled_event_switches(self):
        from test_regressions import ui
        view = self.make()
        view._buzzer_values = ui.BuzzerSettings(enabled=False)
        view._play_buzzer_melody('PRINT_DONE')
        view._emergency_buzzer_feedback()
        view._buzzer_player.play_melody.assert_not_called()
        view._buzzer_player.play_emergency.assert_not_called()
        view._buzzer_values = ui.BuzzerSettings(volume=0)
        view._play_buzzer_melody('PRINT_DONE')
        view._buzzer_player.play_melody.assert_not_called()
        view._emergency_buzzer_feedback()
        view._buzzer_player.play_emergency.assert_called_once()

    def test_synchronous_save_requires_matching_readback(self):
        from test_regressions import ui
        view = self.make()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = False
        target = EventSounds().toggled('NFC_TAG_READ')
        view.lcd.read_flash.return_value = b'wrong'
        with self.assertRaises(ui.T5UIC1ProtocolError):
            view._toggle_event_sound('NFC_TAG_READ')
        self.assertTrue(view._event_sound_enabled('NFC_TAG_READ'))
        view.lcd.read_flash.return_value = target.encode()
        view._toggle_event_sound('NFC_TAG_READ')
        self.assertFalse(view._event_sound_enabled('NFC_TAG_READ'))
