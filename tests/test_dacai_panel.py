import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image, JpegImagePlugin
import serial

from petrel.artwork import sprites
from petrel.artwork.resources import ICON_FAN_FIRST, ICON_FAN_LAST, ICON_LIBRARY_ID
from petrel.hardware.dwin import dacai, protocol
from petrel.hardware.dwin.dacai import DacaiDriver
from petrel.hardware.dwin.driver import T5UIC1Display
from test_t5uic1_driver import driver

ROOT = Path(__file__).resolve().parents[1]


def dacai_driver():
    lcd = driver()
    lcd.__class__ = DacaiDriver
    lcd.host_baud = dacai.DEFAULT_BAUD
    lcd._sprites = None
    lcd._sprite_animations = {}
    lcd._sprite_mask = 0xFFFF
    return lcd


def sent(lcd):
    """(opcode, payload) for every frame written to the fake port."""
    return [(frame[1], frame[2:-4]) for frame in lcd.serial.frames]


class DacaiSelectionTests(unittest.TestCase):
    def test_panel_type_and_baud_come_from_configuration(self):
        with patch.dict('os.environ', {'PETREL_DACAI': '1', 'PETREL_DACAI_BAUD': '460800'}):
            self.assertTrue(dacai.enabled())
            self.assertEqual(dacai.configured_baud(), 460800)
        with patch.dict('os.environ', {'PETREL_DACAI': '0', 'PETREL_DACAI_BAUD': '12345'}):
            self.assertFalse(dacai.enabled())
            self.assertEqual(dacai.configured_baud(), 115200)

    def test_dwin_limits_are_unchanged(self):
        self.assertEqual(T5UIC1Display.PICTURE_ID_MAX, 15)
        self.assertFalse(T5UIC1Display.BARE_FLASH_ACK)
        with self.assertRaises(ValueError):
            driver().cache_jpeg(16)
        self.assertEqual(driver().prepare_picture(b'abc'), b'abc')


class BareFlashAckTests(unittest.TestCase):
    def test_bare_ack_only_when_enabled(self):
        buffer = bytearray(b'\xa5OK')
        self.assertEqual(protocol.take_response(buffer, bare_flash_ack=True), (0x31, b'\xa5OK'))
        self.assertEqual(buffer, bytearray())
        buffer = bytearray(b'\xa5OK')
        self.assertIsNone(protocol.take_response(buffer))

    def test_split_bare_ack_is_kept_for_next_read(self):
        buffer = bytearray(b'noise\xa5O')
        self.assertIsNone(protocol.take_response(buffer, bare_flash_ack=True))
        buffer.extend(b'K')
        self.assertEqual(protocol.take_response(buffer, bare_flash_ack=True), (0x31, b'\xa5OK'))


class DacaiProtocolTests(unittest.TestCase):
    def test_picture_payload_is_32k_jpeg_ending_with_eoi(self):
        payload = dacai.picture_payload(b'\xff\xd8body\xff\xd9')
        self.assertEqual(len(payload), 0x8000)
        self.assertEqual(payload[:4], b'\xff\xd8\xff\xfe')
        self.assertEqual(payload[-2:], b'\xff\xd9')
        with self.assertRaises(ValueError):
            dacai.picture_payload(b'\xff\xd8' + bytes(0x8000) + b'\xff\xd9')
        with self.assertRaises(ValueError):
            dacai.picture_payload(b'not a jpeg')

    def test_sram_jpeg_uses_0x70(self):
        lcd = dacai_driver()
        lcd.show_sram_jpeg(10, 20, 0x100)
        self.assertEqual(sent(lcd), [(0x70, lcd._words(10, 20, 0x100))])

    def test_copy_cache_bit7_is_inverted(self):
        lcd = dacai_driver()
        lcd.copy_cache(1, 0, 0, 9, 9, 5, 5, background=True, enhanced=False)
        lcd.copy_cache(1, 0, 0, 9, 9, 5, 5, background=False, enhanced=False)
        self.assertEqual([payload[0] for _, payload in sent(lcd)], [0x01, 0x81])

    def test_backlight_is_scaled_to_firmware_range(self):
        lcd = dacai_driver()
        for value in (0, 1, 128, 255):
            lcd.set_backlight(value)
        self.assertEqual([payload[0] for _, payload in sent(lcd)], [0, 4, 32, 63])

    def test_picture_ids_above_15_are_accepted(self):
        lcd = dacai_driver()
        lcd.cache_jpeg(200)
        self.assertEqual(sent(lcd), [(0x25, bytes((1, 200)))])


class DacaiBaudTests(unittest.TestCase):
    def link(self, answers):
        lcd = dacai_driver()
        lcd.serial = MagicMock(baudrate=115200)
        lcd.handshake = MagicMock(side_effect=answers)
        lcd._send = MagicMock()
        return lcd

    def test_raises_speed_after_handshake(self):
        lcd = self.link([True])
        with patch('petrel.hardware.dwin.dacai.time.sleep'):
            lcd._switch_baud(460800)
        lcd._send.assert_called_once_with(0x38, lcd._word(34))
        self.assertEqual(lcd.serial.baudrate, 460800)

    def test_falls_back_to_115200_when_panel_stops_answering(self):
        lcd = self.link([False, False, False, True])
        with patch('petrel.hardware.dwin.dacai.time.sleep'):
            lcd._switch_baud(921600)
        self.assertEqual(lcd.serial.baudrate, 115200)
        self.assertEqual(lcd._send.call_args_list[-1].args, (0x38, lcd._word(136)))

    def test_probe_alternates_speeds_only_for_dacai(self):
        port = MagicMock(spec=serial.Serial, baudrate=115200, in_waiting=0)
        port.write.side_effect = len
        from petrel.hardware.dwin.startup import PanelProbe
        with patch('petrel.hardware.dwin.startup.open_display_serial', return_value=port), \
                patch.dict('os.environ', {'PETREL_DACAI': '1', 'PETREL_DACAI_BAUD': '460800'}):
            probe = PanelProbe('/dev/null')
            speeds = []
            for _ in range(3):
                probe.next_send = 0
                probe.poll()
                speeds.append(port.baudrate)
        self.assertEqual(speeds, [460800, 115200, 460800])
        with patch('petrel.hardware.dwin.startup.open_display_serial', return_value=port), \
                patch.dict('os.environ', {'PETREL_DACAI': '0'}):
            self.assertEqual(PanelProbe('/dev/null').alt_baud, 0)


class SpritePackingTests(unittest.TestCase):
    def test_icons_are_grid_aligned_inside_sheet_and_disjoint(self):
        sizes = {1: (20, 20), 2: (110, 100), 3: (252, 24), 4: (1, 52), 5: (244, 202), 6: (20, 20)}
        count, placement = sprites.pack(sizes)
        boxes = {}
        for icon, (sheet, x, y) in placement.items():
            w, h = (sprites._cells(v) for v in sizes[icon])
            self.assertEqual((x % sprites.CELL, y % sprites.CELL), (0, 0))
            self.assertLessEqual(x + w, sprites.SHEET_WIDTH)
            self.assertLessEqual(y + h, sprites.SHEET_HEIGHT)
            for other, (osheet, ox0, oy0, ox1, oy1) in boxes.items():
                if osheet == sheet:
                    self.assertTrue(x >= ox1 or x + w <= ox0 or y >= oy1 or y + h <= oy0,
                                    (icon, other))
            boxes[icon] = (sheet, x, y, x + w, y + h)
        self.assertLess(max(sheet for sheet, *_ in placement.values()), count)

    def test_oversized_icon_is_rejected(self):
        with self.assertRaises(ValueError):
            sprites.pack({1: (300, 20)})


class SpriteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = sprites.build()

    def test_every_sheet_is_a_storable_baseline_420_picture(self):
        self.assertLessEqual(len(self.set.payloads), sprites.MAX_SHEETS)
        for payload in self.set.payloads:
            self.assertLessEqual(len(payload), sprites.MAX_JPEG)
            self.assertEqual(len(dacai.picture_payload(payload)), 0x8000)
            with Image.open(io.BytesIO(payload)) as image:
                self.assertEqual(image.size, (sprites.SHEET_HEIGHT, sprites.SHEET_WIDTH))
                self.assertFalse(image.info.get('progressive'))
                self.assertEqual(JpegImagePlugin.get_sampling(image), 2)

    def test_index_covers_every_used_icon_except_nfc_frames(self):
        for icon in range(ICON_FAN_FIRST, ICON_FAN_LAST + 1):
            self.assertIn(icon, self.set.index)
        self.assertFalse(sprites.SKIPPED_IDS & set(self.set.index))

    def test_metadata_round_trip_and_corruption(self):
        raw = sprites.metadata(self.set.digests)
        self.assertEqual(len(raw), sprites.METADATA_SIZE)
        self.assertEqual(sprites.parse_metadata(raw), list(self.set.digests))
        broken = bytearray(raw)
        broken[20] ^= 1
        self.assertEqual(sprites.parse_metadata(bytes(broken)), [])

    def test_metadata_does_not_overlap_other_flash_records(self):
        from petrel.artwork import boot, icon_library, shared
        from petrel.features.buzzer import control, event_settings
        start, end = sprites.METADATA_ADDRESS, sprites.METADATA_ADDRESS + sprites.METADATA_SIZE
        for address, size in ((boot.ADDRESS, boot.SIZE), (shared.ADDRESS, shared.SIZE),
                              (icon_library.METADATA_ADDRESS, icon_library.METADATA_SIZE),
                              (control.ADDRESS, control.LEGACY_RECORD_SIZE),
                              (event_settings.ADDRESS, event_settings.RECORD_SIZE)):
            self.assertTrue(address + size <= start or address >= end, hex(address))
        self.assertLessEqual(end, T5UIC1Display.FLASH_USABLE_SIZE)


class FakeFlashLcd:
    def __init__(self, stored=b''):
        self.flash = stored
        self.events = []
        self.serial = self

    def read_flash(self, address, size):
        return self.flash

    def write_flash(self, address, data):
        self.events.append(('write_flash', address))
        self.flash = data

    def prepare_picture(self, data):
        return dacai.picture_payload(data)

    def write_sram(self, address, data):
        self.events.append(('write_sram', len(data)))

    def flush(self):
        pass

    def store_sram_as_picture(self, picture_id, timeout):
        self.events.append(('store', picture_id))


class SpriteSyncTests(unittest.TestCase):
    def setUp(self):
        sprites._ATTEMPTS.clear()
        self.set = sprites.SpriteSet([b'\xff\xd8a\xff\xd9', b'\xff\xd8b\xff\xd9'], {})

    def test_first_sync_uploads_all_then_commits_metadata_last(self):
        lcd = FakeFlashLcd()
        with patch('petrel.artwork.sprites.time.sleep'):
            self.assertTrue(sprites.sync(lcd, sprites=self.set))
        self.assertEqual([e for e in lcd.events if e[0] == 'store'],
                         [('store', sprites.FIRST_SLOT), ('store', sprites.FIRST_SLOT + 1)])
        self.assertIn(('write_sram', 0x8000), lcd.events)
        self.assertEqual(lcd.events[-1][0], 'write_flash')
        self.assertTrue(sprites.resident(lcd, self.set))

    def test_unchanged_sheets_are_not_rewritten(self):
        lcd = FakeFlashLcd(sprites.metadata(self.set.digests))
        self.assertFalse(sprites.sync(lcd, sprites=self.set))
        self.assertEqual(lcd.events, [])

    def test_only_changed_sheet_is_uploaded(self):
        lcd = FakeFlashLcd(sprites.metadata([self.set.digests[0], bytes(32)]))
        with patch('petrel.artwork.sprites.time.sleep'):
            sprites.sync(lcd, sprites=self.set)
        self.assertEqual([e for e in lcd.events if e[0] == 'store'], [('store', sprites.FIRST_SLOT + 1)])

    def test_force_rewrites_resident_sheets(self):
        lcd = FakeFlashLcd(sprites.metadata(self.set.digests))
        with patch('petrel.artwork.sprites.time.sleep'):
            self.assertTrue(sprites.sync(lcd, force=True, sprites=self.set))
        self.assertEqual(len([e for e in lcd.events if e[0] == 'store']), 2)


class SpriteDrawingTests(unittest.TestCase):
    def setUp(self):
        self.lcd = dacai_driver()
        self.lcd._sprites = {7: (1, 32, 48, 20, 20), 8: (1, 64, 48, 20, 20), 9: (0, 0, 0, 20, 20)}

    def test_show_icon_copies_from_cached_sheet_in_a_row(self):
        self.lcd.show_icon(ICON_LIBRARY_ID, (7, 8), 100, 200, background=False)
        frames = sent(self.lcd)
        self.assertEqual(frames[0], (0x25, bytes((1, sprites.FIRST_SLOT + 1))))
        self.assertEqual([op for op, _ in frames], [0x25, 0x27, 0x27])
        self.assertEqual(frames[1][1], bytes((0x81,)) + self.lcd._words(32, 48, 51, 67, 100, 200))
        self.assertEqual(frames[2][1][1:], self.lcd._words(64, 48, 83, 67, 120, 200))

    def test_sheet_is_loaded_only_when_it_changes(self):
        self.lcd.show_icon(ICON_LIBRARY_ID, 7, 0, 0)
        self.lcd.show_icon(ICON_LIBRARY_ID, 8, 0, 0)
        self.lcd.show_icon(ICON_LIBRARY_ID, 9, 0, 0)
        self.assertEqual([op for op, _ in sent(self.lcd)], [0x25, 0x27, 0x27, 0x25, 0x27])

    def test_unknown_icon_other_library_or_no_sheets_fall_back_to_0x23(self):
        self.lcd.show_icon(ICON_LIBRARY_ID, 99, 0, 0)
        self.lcd.show_icon(9, 7, 0, 0)
        self.lcd._sprites = None
        self.lcd.show_icon(ICON_LIBRARY_ID, 7, 0, 0)
        self.assertEqual([op for op, _ in sent(self.lcd)], [0x23, 0x23, 0x23])

    def test_animation_is_stepped_by_host_and_wraps(self):
        with patch('petrel.hardware.dwin.dacai.time.monotonic', return_value=100.0):
            self.lcd.configure_animation(1, True, ICON_LIBRARY_ID, 7, 8, 10, 20, 10)
        self.assertNotIn(0x28, [op for op, _ in sent(self.lcd)])
        self.assertEqual(self.lcd._sprite_animations[1]['frame'], 8)
        self.assertAlmostEqual(self.lcd.poll_host_animations(100.05), .05)
        self.lcd.poll_host_animations(100.2)
        self.assertEqual(self.lcd._sprite_animations[1]['frame'], 7)
        self.lcd.configure_animation(1, False, ICON_LIBRARY_ID, 7, 8, 10, 20, 10)
        self.assertEqual(self.lcd._sprite_animations, {})
        self.assertIsNone(self.lcd.poll_host_animations(101))

    def test_resume_keeps_frame_unless_restarted(self):
        self.lcd.configure_animation(1, True, ICON_LIBRARY_ID, 7, 9, 0, 0, 10)
        self.lcd.configure_animation(1, True, ICON_LIBRARY_ID, 7, 9, 0, 0, 20,
                                     restart_from_first=False)
        self.assertEqual(self.lcd._sprite_animations[1]['frame'], 9)

    def test_mask_pauses_host_animation(self):
        self.lcd.set_animation_mask(0)
        self.lcd.configure_animation(2, True, ICON_LIBRARY_ID, 7, 8, 0, 0, 10)
        self.assertIsNone(self.lcd.poll_host_animations(5))
        self.assertEqual(self.lcd._sprite_animations[2]['frame'], 7)

    def test_animation_without_sheets_uses_panel_0x28(self):
        self.lcd._sprites = None
        self.lcd.configure_animation(1, True, ICON_LIBRARY_ID, 7, 8, 0, 0, 10)
        self.assertEqual([op for op, _ in sent(self.lcd)], [0x28])


class DacaiConfigurationTests(unittest.TestCase):
    def test_kconfig_round_trip_and_baud_validation(self):
        from tools.configure import Configuration, collect, defaults, render_env, validate
        values = defaults(Path('/home/pi'))
        values.update(PETREL_DACAI='y', PETREL_DACAI_BAUD='460800')
        validate(values)
        self.assertEqual(collect(Configuration(ROOT, values))['PETREL_DACAI_BAUD'], '460800')
        env = render_env(values, '')
        self.assertIn('PETREL_DACAI=1\n', env)
        self.assertIn('PETREL_DACAI_BAUD=460800\n', env)
        values['PETREL_DACAI_BAUD'] = '250000'
        with self.assertRaises(ValueError):
            validate(values)


if __name__ == '__main__':
    unittest.main()
