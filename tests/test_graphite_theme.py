from lcd_resources import ICON_LIBRARY_ID
import unittest
from unittest.mock import Mock
from PIL import Image, ImageChops
from test_regressions import ui
from test_capabilities import display, snapshot
from test_t5uic1_driver import driver
from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer
from icon_library import metadata, parse_metadata, MAX_BLOCKS, METADATA_ADDRESS, METADATA_SIZE


class GraphiteContracts(unittest.TestCase):
    def test_petrel_wordmark_keeps_empty_matte_filtered_on_any_background(self):
        from dwin_emulator.assets import rgb565
        assets = PanelAssets()
        icon = assets.icon(ICON_LIBRARY_ID, 0)
        self.assertEqual(icon.size, (130, 32))
        for background in (0x2125, 0x0000, 0xFFFF):
            fb = Framebuffer(assets)
            fb.image.paste(rgb565(background), (0, 0, 272, 480))
            # Exercise exactly the compositing mode used by show_theme_icon.
            fb._paste(icon, 71, 48, 0x20)
            for x in (*range(71, 77), *range(192, 201)):
                for y in range(48, 80):
                    self.assertEqual(fb.image.getpixel((x, y)), rgb565(background))
            # No slogan fragment or matte residue below the logo's bowl.
            for x in range(101, 106):
                for y in range(71, 80):
                    self.assertEqual(fb.image.getpixel((x, y)), rgb565(background))
        # The brand contains both its blue/cyan mark and a clean white wordmark.
        self.assertTrue(any(b > 180 and r < 80 for r, g, b in icon.getdata()))
        self.assertTrue(any(min(pixel) > 240 for pixel in icon.getdata()))


    def test_active_resume_label_is_native_and_stays_in_its_lane_in_both_states(self):
        v = display(snapshot())
        v.lcd = driver()
        v.pd.printingIsPaused = Mock(return_value=True)
        for selection in (0, 1):
            v.select_print.set(selection)
            v.lcd.serial.frames.clear()
            v._focus_draw_buttons()
            text = next(f for f in v.lcd.serial.frames
                        if f[1] == 0x11 and f[11:-4] == b'Resume')
            x = int.from_bytes(text[7:9], 'big')
            self.assertEqual(x, 128)
            self.assertGreaterEqual(x, 97 + 31)
            self.assertLessEqual(x + 6 * len('Resume'), 175)

    def test_sound_rows_have_four_distinct_icons_and_light_is_not_brightness(self):
        v = display(snapshot())
        v._buzzer_rows = Mock(return_value=[('Buzzer','Buzzer',False),('Volume','60%',True),
                                          ('Click tone','Tick',True),('Encoder tone','Tick',True)])
        v._buzzer_enabled = Mock(return_value=True)
        v._draw_list_menu = Mock()
        v.Draw_Display_Menu()
        rows = v._draw_list_menu.call_args.args[1]
        self.assertEqual([r[1] for r in rows[4:8]], [159, 160, 161, 162])
        # Brightness artwork only belongs to PWM-capable case lights.
        data = snapshot()
        data['objects'].append('output_pin case_light')
        data['settings']['output_pin case_light'] = {'pwm': True}
        v.pd.subscription.snapshot.return_value = data
        v.pd.update_variable()
        v.Draw_Case_Light_Menu()
        rows = v._draw_list_menu.call_args.args[1]
        self.assertEqual([r[1] for r in rows[1:]], [155, 156])
        self.assertNotEqual(v.ICON_CloseMotor, 111)  # Motor-off is not an MCU chip.
        self.assertNotEqual(v.ICON_Motion, v.ICON_CaseLight)

    def test_metadata_for_all_reserved_slots_stays_before_buzzer_record(self):
        hashes = [bytes([i]) * 32 for i in range(MAX_BLOCKS)]
        raw = metadata(hashes)
        self.assertEqual(len(raw), METADATA_SIZE)
        self.assertEqual(parse_metadata(raw), hashes)
        self.assertEqual(METADATA_ADDRESS + len(raw), 0x0400)

    def test_boot_overlay_preserves_artwork_outside_its_ink(self):
        v = display(snapshot()); v.lcd = driver()
        model = Framebuffer(PanelAssets()); v.lcd._packet_observer = model
        v.lcd.show_jpeg(0); v.lcd.update(); base = model.snapshot()[0]
        v._boot_progress = -1
        v._draw_boot_progress(70)
        image = model.snapshot()[0]; diff = ImageChops.difference(base, image)
        for y in range(480):
            if not (292 <= y <= 299 or 320 <= y <= 339):
                self.assertIsNone(diff.crop((0, y, 272, y+1)).getbbox(), y)

    def test_selected_update_button_has_dark_text_on_cyan(self):
        v = display(snapshot()); v.lcd = driver()
        v._software_updater = Mock(return_value=Mock(label='Check for updates', message=''))
        v._draw_info_update_button(332, True)
        text = next(f for f in v.lcd.serial.frames if f[1] == 0x11)
        self.assertEqual(int.from_bytes(text[3:5], 'big'), 0x10C4)
        self.assertEqual(int.from_bytes(text[5:7], 'big'), 0x063B)

    def test_animation_uses_existing_library_during_migration_and_waits_for_empty_directory(self):
        from t5uic1_driver import T5UIC1Display
        from icon_library import MAGIC
        import zlib
        lcd = T5UIC1Display.__new__(T5UIC1Display)
        lcd.read_flash = Mock()
        def resident(library, committed=True):
            hashes = (b'x' * 32 if committed else bytes(32)) + b'y' * (7 * 32)
            body = (MAGIC + bytes((library, 8)) + hashes).ljust(508, b'\x00')
            return body + zlib.crc32(body).to_bytes(4, 'big')
        for library in (7, 3, ICON_LIBRARY_ID):
            with self.subTest(library=library):
                lcd.read_flash.return_value = resident(library)
                self.assertEqual(lcd._startup_animation_library(), library)
                lcd.read_flash.return_value = resident(library, committed=False)
                self.assertIsNone(lcd._startup_animation_library())
                damaged = bytearray(resident(library)); damaged[20] ^= 1
                lcd.read_flash.return_value = bytes(damaged)
                self.assertIsNone(lcd._startup_animation_library())
        lcd.read_flash.return_value = resident(4)
        self.assertIsNone(lcd._startup_animation_library())

