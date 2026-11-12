import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from PIL import Image, ImageChops, ImageStat, JpegImagePlugin
import serial

from petrel.artwork import sprites
from petrel.artwork.icon_library import SOURCE_DIRECTORY
from petrel.artwork.resources import (
    ICON_FAN_FIRST, ICON_FAN_LAST, ICON_LIBRARY_ID, ICON_NFC_CARD_FIRST, ICON_NFC_CARD_LAST,
    ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST, ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST)
from petrel.hardware.dwin import dacai, protocol
from petrel.hardware.dwin.dacai import DacaiDriver, UnsupportedPanelFeature
from petrel.hardware.dwin.driver import T5UIC1Display
from test_t5uic1_driver import driver

ROOT = Path(__file__).resolve().parents[1]
NFC_RANGES = ((ICON_NFC_CARD_FIRST, ICON_NFC_CARD_LAST),
              (ICON_NFC_SHARE_FIRST, ICON_NFC_SHARE_LAST),
              (ICON_NFC_SPOOL_FIRST, ICON_NFC_SPOOL_LAST))


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


def piece(sheet, x, y, width, height, dx=0, dy=0):
    return (sheet, x, y, width, height, dx, dy)


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
        self.assertEqual(T5UIC1Display.PANEL_PROTOCOL, 'dwin')
        self.assertFalse(T5UIC1Display.OPAQUE_SRAM_JPEG)
        with self.assertRaises(ValueError):
            driver().cache_jpeg(16)
        self.assertEqual(driver().prepare_picture(b'abc'), b'abc')

    def test_dacai_capabilities(self):
        self.assertEqual(DacaiDriver.PANEL_PROTOCOL, 'dacai')
        self.assertTrue(DacaiDriver.OPAQUE_SRAM_JPEG)


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

    def test_copy_cache_sends_the_last_row_one_lower(self):
        # Measured: the panel copies rows y0..y1+1 (columns x0..x1 exactly).
        lcd = dacai_driver()
        lcd.copy_cache(1, 10, 20, 29, 39, 5, 6)
        lcd.copy_cache(1, 10, 20, 29, 20, 5, 6)  # one row
        lcd.copy_cache(1, 10, 0, 29, 0, 5, 6)    # one row at y = 0: best effort
        self.assertEqual([payload[1:] for _, payload in sent(lcd)],
                         [lcd._words(10, 20, 29, 38, 5, 6), lcd._words(10, 20, 29, 19, 5, 6),
                          lcd._words(10, 0, 29, 0, 5, 6)])

    def test_backlight_is_scaled_to_firmware_range(self):
        lcd = dacai_driver()
        for value in (0, 1, 128, 255):
            lcd.set_backlight(value)
        self.assertEqual([payload[0] for _, payload in sent(lcd)], [0, 4, 32, 63])

    def test_picture_ids_above_15_are_accepted(self):
        lcd = dacai_driver()
        lcd.cache_jpeg(200)
        self.assertEqual(sent(lcd), [(0x25, bytes((1, 200)))])


def polyline_frames(lcd):
    """(color, [(x, y), ...]) for every 0x03 frame written to the fake port."""
    frames = []
    for opcode, payload in sent(lcd):
        assert opcode == 0x03, hex(opcode)
        words = [int.from_bytes(payload[i:i + 2], 'big') for i in range(0, len(payload), 2)]
        frames.append((words[0], list(zip(words[1::2], words[2::2]))))
    return frames


SEGMENTS = ((20, 40, 120, 140), (140, 40, 260, 70), (150, 80, 175, 200),
            (16, 210, 256, 211), (41, 160, 54, 168), (41, 168, 54, 160),
            (120, 140, 20, 40), (260, 70, 140, 40), (175, 200, 150, 80),
            (0, 0, 1, 1), (5, 5, 4, 9))


class DacaiDiagonalLineTests(unittest.TestCase):
    """0x03 on DACAI joins two points by an L-shaped step (#38)."""

    def assert_axis_aligned(self, path):
        for (x0, y0), (x1, y1) in zip(path, path[1:]):
            self.assertTrue((x0 == x1) != (y0 == y1), (path, (x0, y0), (x1, y1)))

    def test_axis_aligned_segments_are_unchanged(self):
        self.assertEqual(dacai.staircase(3, 7, 90, 7), [(3, 7), (90, 7)])
        self.assertEqual(dacai.staircase(3, 90, 3, 7), [(3, 90), (3, 7)])

    def test_known_staircases(self):
        self.assertEqual(dacai.staircase(16, 33, 256, 34),
                         [(16, 33), (135, 33), (135, 34), (256, 34)])
        self.assertEqual(dacai.staircase(0, 0, 3, 3),
                         [(0, 0), (0, 1), (1, 1), (1, 2), (2, 2), (2, 3), (3, 3)])

    def test_staircase_follows_the_segment(self):
        for x0, y0, x1, y1 in SEGMENTS:
            with self.subTest(segment=(x0, y0, x1, y1)):
                path = dacai.staircase(x0, y0, x1, y1)
                self.assertEqual((path[0], path[-1]), ((x0, y0), (x1, y1)))
                self.assert_axis_aligned(path)
                steep = abs(y1 - y0) > abs(x1 - x0)
                # Work along the major axis: (major, minor) coordinates.
                axes = (lambda x, y: (y, x)) if steep else (lambda x, y: (x, y))
                (m0, n0), (m1, n1) = axes(x0, y0), axes(x1, y1)
                covered = {}
                for a, b in zip(path, path[1:]):
                    (am, an), (bm, bn) = axes(*a), axes(*b)
                    # Minor-axis moves are single pixel steps.
                    self.assertIn(abs(bn - an), (0, 1))
                    for m in range(min(am, bm), max(am, bm) + 1):
                        for n in range(min(an, bn), max(an, bn) + 1):
                            covered.setdefault(m, set()).add(n)
                self.assertEqual(sorted(covered), list(range(min(m0, m1), max(m0, m1) + 1)))
                for m, minor in covered.items():
                    ideal = n0 + (m - m0) * (n1 - n0) / (m1 - m0)
                    deviations = [abs(n - ideal) for n in minor]
                    # One pixel per column on the line, plus at most the step corner.
                    self.assertLessEqual(min(deviations), 0.5 + 1e-9)
                    self.assertLess(max(deviations), 1.5)
                    self.assertLessEqual(len(minor), 2)

    def test_horizontal_and_vertical_lines_send_the_dwin_packet(self):
        lcd = dacai_driver()
        reference = driver()
        for line in ((0xFFFF, 0, 50, 271, 50), (0x1234, 10, 0, 10, 479)):
            lcd.draw_line(*line)
            reference.draw_line(*line)
        self.assertEqual(sent(lcd), [(frame[1], frame[2:-4]) for frame in reference.serial.frames])

    def test_diagonal_is_sent_as_axis_aligned_staircase(self):
        lcd = dacai_driver()
        lcd.draw_line(0x07E0, 41, 160, 54, 168)
        [(color, points)] = polyline_frames(lcd)
        self.assertEqual(color, 0x07E0)
        self.assertEqual(points, dacai.staircase(41, 160, 54, 168))
        self.assert_axis_aligned(points)

    def test_polyline_segments_are_joined_without_repeated_points(self):
        lcd = dacai_driver()
        lcd.draw_polyline(0xFFFF, ((41, 160), (47, 164), (54, 160)))
        [(_, points)] = polyline_frames(lcd)
        expected = dacai.staircase(41, 160, 47, 164) + dacai.staircase(47, 164, 54, 160)[1:]
        self.assertEqual(points, expected)
        self.assert_axis_aligned(points)

    def test_long_staircases_are_split_into_frames_sharing_end_points(self):
        lcd = dacai_driver()
        lcd.draw_line(0xF800, 0, 0, 200, 200)
        frames = polyline_frames(lcd)
        self.assertGreater(len(frames), 1)
        for (_, before), (_, after) in zip(frames, frames[1:]):
            self.assertEqual(before[-1], after[0])
        for opcode, payload in sent(lcd):
            self.assertLessEqual(len(payload), lcd.MAX_DATA_LENGTH)
        joined = frames[0][1] + [point for _, points in frames[1:] for point in points[1:]]
        self.assertEqual(joined, dacai.staircase(0, 0, 200, 200))
        self.assertEqual({color for color, _ in frames}, {0xF800})

    def test_invalid_polylines_are_rejected_before_sending(self):
        lcd = dacai_driver()
        for points in (((1, 1),), ((1, 1), (2,)), ((1, 1), 5)):
            with self.subTest(points=points), self.assertRaises(ValueError):
                lcd.draw_polyline(0xFFFF, points)
        self.assertEqual(sent(lcd), [])


class DacaiAuxiliaryUartTests(unittest.TestCase):
    def test_inherited_auxiliary_uart_methods_are_rejected(self):
        lcd = dacai_driver()
        for call in (lambda: lcd.set_aux_baud_divisor(1), lambda: lcd.set_aux_baudrate(115200),
                     lambda: lcd.aux_write(b'x'), lcd.poll_aux_data):
            with self.assertRaises(UnsupportedPanelFeature):
                call()
        self.assertEqual(sent(lcd), [])

    def test_broker_transport_is_rejected_before_the_uart_is_opened(self):
        environment = {'PETREL_DACAI': '1', 'PETREL_DWIN_SOCKET': '/run/petrel-dwin/display.sock'}
        with patch.dict('os.environ', environment), \
                patch('petrel.hardware.dwin.driver.open_display_serial') as opened:
            with self.assertRaises(UnsupportedPanelFeature):
                DacaiDriver('/dev/ttyS0')
            opened.assert_not_called()
        with patch.dict('os.environ', {'PETREL_DACAI': '0', 'PETREL_DWIN_SOCKET': '/x'}):
            dacai.check_transport()  # DWIN with broker stays supported

    def test_service_refuses_to_start_with_dacai_and_broker(self):
        import run
        environment = {'PETREL_DACAI': '1', 'PETREL_DWIN_SOCKET': '/run/petrel-dwin/display.sock'}
        with patch.dict('os.environ', environment), patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                run.parse_args(['--serial-port', '/dev/ttyS0'])
        with patch.dict('os.environ', {'PETREL_DACAI': '1'}):
            os.environ.pop('PETREL_DWIN_SOCKET', None)
            run.parse_args(['--serial-port', '/dev/ttyS0'])


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

    def probe_speeds(self, environment, sends):
        port = MagicMock(spec=serial.Serial, baudrate=115200, in_waiting=0)
        port.write.side_effect = len
        from petrel.hardware.dwin.startup import PanelProbe
        with patch('petrel.hardware.dwin.startup.open_display_serial', return_value=port), \
                patch.dict('os.environ', environment):
            probe = PanelProbe('/dev/null')
            speeds = []
            for _ in range(sends):
                probe.next_send = 0
                probe.poll()
                speeds.append(port.baudrate)
        return speeds

    def test_probe_cycles_all_host_speeds_configured_first(self):
        self.assertEqual(self.probe_speeds({'PETREL_DACAI': '1', 'PETREL_DACAI_BAUD': '460800'}, 5),
                         [460800, 115200, 230400, 921600, 460800])

    def test_probe_finds_a_speed_left_by_an_interrupted_session(self):
        # Killed at 460800, then reconfigured to 921600 or back to 115200.
        for configured in ('921600', '115200'):
            with self.subTest(configured=configured):
                speeds = self.probe_speeds({'PETREL_DACAI': '1', 'PETREL_DACAI_BAUD': configured}, 4)
                self.assertEqual(speeds[0], int(configured))
                self.assertIn(460800, speeds)

    def test_probe_keeps_115200_for_dwin(self):
        self.assertEqual(self.probe_speeds({'PETREL_DACAI': '0'}, 3), [115200] * 3)

    def test_link_ends_at_the_configured_speed_after_probing(self):
        for found, configured in ((460800, 921600), (460800, 115200), (115200, 460800)):
            with self.subTest(found=found, configured=configured):
                lcd = self.link([True])
                lcd.serial = MagicMock(spec=serial.Serial, baudrate=found)
                lcd.host_baud = configured
                with patch('petrel.hardware.dwin.dacai.time.sleep'):
                    lcd._after_handshake()
                self.assertEqual(lcd.serial.baudrate, configured)
                lcd._send.assert_called_once_with(0x38, lcd._word(round(dacai.UART_CLOCK / configured)))
        lcd = self.link([True])
        lcd.serial = MagicMock(spec=serial.Serial, baudrate=460800)
        lcd.host_baud = 460800
        lcd._after_handshake()
        lcd._send.assert_not_called()


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


def sources():
    images = {}
    for path in SOURCE_DIRECTORY.iterdir():
        if path.suffix.lower() == '.jpg' and path.stem[:3].isdigit():
            with Image.open(path) as image:
                images[int(path.stem[:3])] = image.convert('RGB')
    return images


def compose(sheets, pieces):
    """Draw an icon from decoded sheets the way DacaiDriver does."""
    width, height = pieces[0][3], pieces[0][4]
    icon = Image.new('RGB', (width, height))
    for sheet, x, y, w, h, dx, dy in pieces:
        icon.paste(sheets[sheet].crop((x, y, x + w, y + h)), (dx, dy))
    return icon


class SpriteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = sprites.build()
        cls.sheets = []
        for payload in cls.set.payloads:
            with Image.open(io.BytesIO(payload)) as image:
                cls.sheets.append(image.convert('RGB').rotate(-90, expand=True))
        cls.sources = sources()

    def test_every_sheet_is_a_storable_baseline_420_picture(self):
        self.assertLessEqual(len(self.set.payloads), sprites.MAX_SHEETS)
        for payload in self.set.payloads:
            self.assertLessEqual(len(payload), sprites.MAX_JPEG)
            self.assertEqual(len(dacai.picture_payload(payload)), 0x8000)
            with Image.open(io.BytesIO(payload)) as image:
                self.assertEqual(image.size, (sprites.SHEET_HEIGHT, sprites.SHEET_WIDTH))
                self.assertFalse(image.info.get('progressive'))
                self.assertEqual(JpegImagePlugin.get_sampling(image), 2)

    def test_index_covers_every_icon_including_nfc_frames(self):
        self.assertEqual(set(self.set.index), set(self.sources))
        for icon in range(ICON_FAN_FIRST, ICON_FAN_LAST + 1):
            self.assertIn(icon, self.set.index)
        for first, last in NFC_RANGES:
            for icon in range(first, last + 1):
                self.assertIn(icon, self.set.index)

    def test_nfc_frames_are_first_frame_plus_patch(self):
        for first, last in NFC_RANGES:
            base = self.set.index[first]
            self.assertEqual(len(base), 1)
            for icon in range(first + 1, last + 1):
                pieces = self.set.index[icon]
                self.assertEqual(pieces[0], base[0])
                for sheet, x, y, w, h, dx, dy in pieces:
                    self.assertLessEqual(dx + w, base[0][3])
                    self.assertLessEqual(dy + h, base[0][4])

    def test_patches_sit_on_the_jpeg_grid_of_their_frame(self):
        # Sheet and frame grid coincide, so a patch block never mixes in
        # neighbouring sheet content (visible as lines on the panel).
        for first, last in NFC_RANGES:
            for icon in range(first + 1, last + 1):
                for sheet, x, y, w, h, dx, dy in self.set.index[icon][1:]:
                    self.assertEqual(((x - dx) % sprites.CELL, (y - dy) % sprites.CELL), (0, 0), icon)

    def test_patch_borders_inside_the_frame_do_not_bleed(self):
        # A patch edge inside the frame showed as a line on the panel. (Edges on
        # the frame border are the icon outline, like every other sprite.)
        for first, last in NFC_RANGES:
            for icon in range(first + 1, last + 1):
                base = self.set.index[first][0]
                drawn = compose(self.sheets, self.set.index[icon])
                error = ImageChops.difference(drawn, self.sources[icon]).convert('L')
                for sheet, x, y, w, h, dx, dy in self.set.index[icon][1:]:
                    edges = [box for inside, box in (
                        (dy > 0, (dx, dy, dx + w, dy + 1)),
                        (dy + h < base[4], (dx, dy + h - 1, dx + w, dy + h)),
                        (dx > 0, (dx, dy, dx + 1, dy + h)),
                        (dx + w < base[3], (dx + w - 1, dy, dx + w, dy + h))) if inside]
                    for box in edges:
                        self.assertLess(ImageStat.Stat(error.crop(box)).mean[0], 4, (icon, box))

    def test_identical_frames_share_their_pieces(self):
        for icon, original in ((50, 49), (122, 121), (136, 135)):
            self.assertEqual(self.sources[icon].tobytes(), self.sources[original].tobytes())
            self.assertEqual(self.set.index[icon], self.set.index[original])

    def test_composed_icons_match_their_sources(self):
        for first, last in NFC_RANGES + ((ICON_FAN_FIRST, ICON_FAN_LAST),):
            for icon in range(first, last + 1):
                source = self.sources[icon]
                drawn = compose(self.sheets, self.set.index[icon])
                self.assertEqual(drawn.size, source.size)
                error = ImageChops.difference(drawn, source).convert('L')
                self.assertLess(ImageStat.Stat(error).mean[0], 6, icon)

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
        self.corrupt_writes = False

    def read_flash(self, address, size):
        return self.flash

    def write_flash(self, address, data):
        self.events.append(('write_flash', address))
        self.flash = bytes(len(data)) if self.corrupt_writes else data

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


class SpriteStartupStateTests(unittest.TestCase):
    """Artwork counts as synchronized only after a verified upload."""

    def setUp(self):
        sprites._ATTEMPTS.clear()
        self.set = sprites.SpriteSet([b'\xff\xd8a\xff\xd9'], {7: (piece(0, 0, 0, 20, 20),)})
        self.flash = FakeFlashLcd()
        self.lcd = dacai_driver()
        self.lcd.read_flash = self.flash.read_flash
        self.lcd.write_flash = self.flash.write_flash
        self.lcd.write_sram = self.flash.write_sram
        self.lcd.store_sram_as_picture = self.flash.store_sram_as_picture
        self.lcd.serial.flush = lambda: None

    def sync(self):
        with patch('petrel.artwork.sprites.load', return_value=self.set), \
                patch('petrel.artwork.sprites.time.sleep'):
            self.lcd._startup_sync_icons()

    def test_failed_metadata_verification_fails_startup(self):
        self.flash.corrupt_writes = True
        with self.assertRaisesRegex(RuntimeError, 'metadata verification failed'):
            self.sync()
        self.assertFalse(getattr(self.lcd, '_assets_synced', False))
        self.assertIsNone(self.lcd._sprites)
        # Icons are not silently drawn from the panel's own icon files.
        self.lcd.show_icon(ICON_LIBRARY_ID, 7, 0, 0)
        self.assertNotIn(0x27, [op for op, _ in sent(self.lcd)])

    def test_failed_upload_fails_startup(self):
        self.lcd.store_sram_as_picture = Mock(side_effect=TimeoutError('no ack'))
        with self.assertRaises(TimeoutError):
            self.sync()
        self.assertFalse(getattr(self.lcd, '_assets_synced', False))
        self.assertIsNone(self.lcd._sprites)

    def test_verified_upload_marks_assets_synchronized(self):
        self.sync()
        self.assertTrue(self.lcd._assets_synced)
        self.assertEqual(self.lcd._sprites, self.set.index)

    def test_failed_resync_drops_the_previous_sheets(self):
        self.sync()
        self.flash.corrupt_writes = True
        with patch('petrel.artwork.sprites.load', return_value=self.set), \
                patch('petrel.artwork.sprites.time.sleep'), self.assertRaises(RuntimeError):
            self.lcd.sync_sprites(force=True)
        self.assertIsNone(self.lcd._sprites)


class SpriteDrawingTests(unittest.TestCase):
    def setUp(self):
        self.lcd = dacai_driver()
        self.lcd._sprites = {7: (piece(1, 32, 48, 20, 20),), 8: (piece(1, 64, 48, 20, 20),),
                             9: (piece(0, 0, 0, 20, 20),),
                             10: (piece(1, 32, 48, 20, 20), piece(0, 32, 0, 8, 6, 4, 5))}

    def test_show_icon_copies_from_cached_sheet_in_a_row(self):
        self.lcd.show_icon(ICON_LIBRARY_ID, (7, 8), 100, 200, background=False)
        frames = sent(self.lcd)
        self.assertEqual(frames[0], (0x25, bytes((1, sprites.FIRST_SLOT + 1))))
        self.assertEqual([op for op, _ in frames], [0x25, 0x27, 0x27])
        self.assertEqual(frames[1][1], bytes((0x81,)) + self.lcd._words(32, 48, 51, 66, 100, 200))
        self.assertEqual(frames[2][1][1:], self.lcd._words(64, 48, 83, 66, 120, 200))

    def test_patched_frame_draws_base_then_patch_at_offset(self):
        self.lcd.show_icon(ICON_LIBRARY_ID, (10, 7), 100, 200)
        frames = [(op, payload) for op, payload in sent(self.lcd) if op == 0x27]
        self.assertEqual(frames[0][1][1:], self.lcd._words(32, 48, 51, 66, 100, 200))
        self.assertEqual(frames[1][1][1:], self.lcd._words(32, 0, 39, 4, 104, 205))
        # The next icon follows the full width of the patched frame.
        self.assertEqual(frames[2][1][1:], self.lcd._words(32, 48, 51, 66, 120, 200))

    def test_sheet_is_loaded_only_when_it_changes(self):
        self.lcd.show_icon(ICON_LIBRARY_ID, 7, 0, 0)
        self.lcd.show_icon(ICON_LIBRARY_ID, 8, 0, 0)
        self.lcd.show_icon(ICON_LIBRARY_ID, 9, 0, 0)
        self.assertEqual([op for op, _ in sent(self.lcd)], [0x25, 0x27, 0x27, 0x25, 0x27])

    def test_missing_icon_is_skipped_instead_of_using_panel_icon_files(self):
        with self.assertLogs(level='WARNING'):
            self.lcd.show_icon(ICON_LIBRARY_ID, (99, 7), 0, 0)
        self.assertEqual([op for op, _ in sent(self.lcd)], [0x25, 0x27])

    def test_other_library_or_no_sheets_use_0x23(self):
        self.lcd.show_icon(9, 7, 0, 0)
        self.lcd._sprites = None
        self.lcd.show_icon(ICON_LIBRARY_ID, 7, 0, 0)
        self.assertEqual([op for op, _ in sent(self.lcd)], [0x23, 0x23])

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

    def test_animation_with_missing_frames_never_uses_panel_0x28(self):
        with self.assertLogs(level='WARNING'):
            self.lcd.configure_animation(1, True, ICON_LIBRARY_ID, 7, 12, 0, 0, 10)
        self.assertEqual(sent(self.lcd), [])
        self.assertEqual(self.lcd._sprite_animations, {})

    def test_animation_without_sheets_uses_panel_0x28(self):
        self.lcd._sprites = None
        self.lcd.configure_animation(1, True, ICON_LIBRARY_ID, 7, 8, 0, 0, 10)
        self.assertEqual([op for op, _ in sent(self.lcd)], [0x28])


class HostNfcReaderTests(unittest.TestCase):
    """NFC readers on the host (UART, I2C, SPI, USB) need no display auxiliary UART."""

    @classmethod
    def setUpClass(cls):
        cls.index = sprites.build().index

    def test_nfc_animations_are_host_stepped_from_the_sheets(self):
        lcd = dacai_driver()
        lcd._sprites = self.index
        for animation_id, (first, last) in enumerate(NFC_RANGES, start=3):
            lcd.configure_animation(animation_id, True, ICON_LIBRARY_ID, first, last, 56, 116, 20)
            self.assertIn(animation_id, lcd._sprite_animations)
        for step in range(13):
            lcd.poll_host_animations(1000 + step)
        opcodes = {op for op, _ in sent(lcd)}
        self.assertNotIn(0x28, opcodes)
        self.assertNotIn(0x23, opcodes)
        self.assertIn(0x27, opcodes)
        self.assertEqual(len(lcd._sprite_animations), 3)

    def test_nfc_card_icon_is_drawn_from_the_sheets(self):
        lcd = dacai_driver()
        lcd._sprites = self.index
        lcd.show_icon(ICON_LIBRARY_ID, ICON_NFC_SPOOL_LAST, 56, 116)
        self.assertEqual({op for op, _ in sent(lcd)} - {0x25}, {0x27})


class DacaiEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from petrel.emulator.assets import PanelAssets
        cls.assets = PanelAssets()

    def model(self, protocol):
        from petrel.emulator.framebuffer import Framebuffer
        model = Framebuffer(self.assets)
        model.reset(protocol=protocol)
        lcd = dacai_driver() if protocol == 'dacai' else driver()
        lcd._packet_observer = model
        return model, lcd

    def jpeg(self, color, size=(16, 16)):
        buffer = io.BytesIO()
        Image.new('RGB', size, color).save(buffer, 'JPEG', quality=95)
        return buffer.getvalue()

    def test_thumbnail_0x70_is_drawn_opaque(self):
        model, lcd = self.model('dacai')
        model.sram[0x100:0x100 + len(self.jpeg((0, 0, 0)))] = self.jpeg((0, 0, 0))
        model.image.paste((200, 200, 200), (0, 0, 272, 480))
        lcd.show_sram_jpeg(40, 50, 0x100)
        lcd.update()
        image, _ = model.snapshot()
        self.assertLess(max(image.getpixel((48, 58))), 16)  # black is not transparent
        self.assertGreater(min(image.getpixel((60, 58))), 150)
        self.assertFalse(model.errors)

    def test_0x70_stays_unsupported_for_dwin(self):
        model, _ = self.model('dwin')
        with self.assertRaises(NotImplementedError):
            model.feed(b'\xaa\x70' + bytes(6) + model.TAIL)

    def test_area_copy_bit7_follows_the_dacai_meaning(self):
        model, lcd = self.model('dacai')
        model.areas[1] = Image.new('RGB', (272, 480), (0, 0, 0))
        model.areas[1].paste((250, 0, 0), (10, 0, 20, 10))
        model.image.paste((0, 0, 250), (0, 0, 272, 480))
        lcd.copy_cache(1, 0, 0, 19, 9, 100, 100, background=False, enhanced=False)  # transparent
        lcd.copy_cache(1, 0, 0, 19, 9, 100, 200, background=True, enhanced=False)   # opaque
        lcd.update()
        image, _ = model.snapshot()
        self.assertEqual(image.getpixel((102, 102)), (0, 0, 250))
        self.assertGreater(image.getpixel((115, 102))[0], 200)
        self.assertLess(max(image.getpixel((102, 202))), 16)
        self.assertGreater(image.getpixel((115, 202))[0], 200)

    def test_area_copy_draws_exactly_the_requested_rows(self):
        # The emulator copies one row more like the panel; the driver compensates.
        model, lcd = self.model('dacai')
        model.areas[1] = Image.new('RGB', (272, 480), (250, 0, 0))
        model.areas[1].paste((0, 250, 0), (0, 0, 20, 10))
        model.image.paste((0, 0, 250), (0, 0, 272, 480))
        lcd.copy_cache(1, 0, 0, 19, 9, 100, 100, background=True)
        lcd.update()
        image, _ = model.snapshot()
        self.assertEqual(image.getpixel((110, 109)), (0, 250, 0))
        self.assertEqual(image.getpixel((110, 110)), (0, 0, 250))
        self.assertEqual(image.getpixel((120, 105)), (0, 0, 250))
        self.assertFalse(model.errors)

    def test_resident_sprite_sheets_render_icons(self):
        model, lcd = self.model('dacai')
        lcd._sprites = sprites.build().index
        lcd.show_icon(ICON_LIBRARY_ID, ICON_NFC_CARD_FIRST + 5, 56, 116)
        lcd.update()
        image, _ = model.snapshot()
        self.assertFalse(model.errors)
        crop = image.crop((56, 116, 216, 276))
        source = sources()[ICON_NFC_CARD_FIRST + 5]
        error = ImageChops.difference(crop, source).convert('L')
        self.assertLess(ImageStat.Stat(error).mean[0], 8)

    def test_driver_announces_its_protocol_to_the_emulator(self):
        from petrel.emulator.runtime import Emulator
        emulator = Emulator(True)
        emulator.reset_panel(protocol='dacai')
        self.assertEqual(emulator.model.protocol, 'dacai')
        emulator.reset_panel()
        self.assertEqual(emulator.model.protocol, 'dwin')
        with self.assertRaises(ValueError):
            emulator.model.reset(protocol='other')


class OpaqueThumbnailTests(unittest.TestCase):
    def thumb(self, size, opaque):
        from petrel.features.files.thumbnail_preview import image_jpeg
        source = Image.new('RGBA', (64, 32), (0, 0, 0, 0))
        source.paste((250, 120, 0, 255), (16, 8, 48, 24))
        buffer = io.BytesIO()
        source.save(buffer, 'PNG')
        return Image.open(io.BytesIO(image_jpeg(buffer.getvalue(), size=size,
                                                opaque=opaque))).convert('RGB')

    def test_opaque_thumbnails_sit_on_the_ui_background(self):
        from petrel.ui.theme import BACKGROUND_COLOR
        corner = self.thumb(128, True).getpixel((2, 2))
        rgb565 = ((corner[0] >> 3) << 11) | ((corner[1] >> 2) << 5) | (corner[2] >> 3)
        self.assertEqual(rgb565, BACKGROUND_COLOR, corner)
        self.assertLess(max(self.thumb(128, False).getpixel((2, 2))), 12)

    def test_print_tile_keeps_its_artwork(self):
        tile = self.thumb(88, True)
        centre_edge = tile.getpixel((44, 4))
        self.assertGreater(max(centre_edge), 30)

    def test_panel_type_environment_does_not_change_thumbnails(self):
        with patch.dict('os.environ', {'PETREL_DACAI': '1'}):
            self.assertLess(max(self.thumb(128, False).getpixel((2, 2))), 12)

    def test_cache_passes_the_panel_capability_to_the_loader(self):
        from concurrent.futures import Future
        from petrel.features.files import thumbnail_cache
        cache = thumbnail_cache.ThumbnailCache(Mock())
        cache.opaque = True
        with patch.object(thumbnail_cache, 'load_preview', return_value='preview') as load, \
                patch.object(thumbnail_cache, 'Thread') as thread:
            future = cache._load_async(('a.gcode', 1, 2, None, 88))
            thread.call_args.kwargs['target']()
        load.assert_called_once_with(cache.client, 'a.gcode', opaque=True, size=88)
        self.assertIsInstance(future, Future)


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

    def test_dacai_and_auxiliary_uart_are_mutually_exclusive(self):
        from tools.configure import Configuration, collect, defaults, validate
        values = defaults(Path('/home/pi'))
        values.update(PETREL_DACAI='y', PETREL_AUX_UART='y')
        with self.assertRaisesRegex(ValueError, 'auxiliary UART'):
            validate(values)
        kconf = Configuration(ROOT, values)
        self.assertEqual(kconf.syms['PETREL_AUX_UART'].visibility, 0)
        self.assertEqual(collect(kconf)['PETREL_AUX_UART'], 'n')
        kconf.syms['PETREL_DACAI'].set_value('n')
        self.assertEqual(collect(kconf)['PETREL_AUX_UART'], 'y')

    def apply(self, home, original, values, manifest):
        from tools.configure import apply
        axis, dwin, nfc = Mock(return_value=False), Mock(), Mock()
        apply(values, repo=ROOT, home=home, user='user', original=original, axis=axis,
              dwin=dwin, nfc=nfc, dwin_manifest=manifest, nfc_manifest=home / 'no-nfc')
        return dwin

    def test_fresh_dacai_configuration_installs_no_broker(self):
        from tools.configure import Configuration, collect, defaults
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            values = defaults(home)
            values.update(PETREL_AXIS_TRAVEL='n', PETREL_DACAI='y')
            dwin = self.apply(home, '', collect(Configuration(ROOT, values)), home / 'none')
            dwin.assert_not_called()
            env = (home / '.config/Petrel/Petrel.env').read_text()
            self.assertIn('PETREL_DACAI=1\n', env)
            self.assertIn('PETREL_AUX_UART=0\n', env)

    def test_switching_to_dacai_removes_an_installed_broker(self):
        from tools.configure import Configuration, collect, read_settings
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/Petrel/Petrel.env'
            path.parent.mkdir(parents=True)
            path.write_text('PETREL_AXIS_TRAVEL=0\nPETREL_AUX_UART=1\n'
                            'PETREL_SERIAL_PORT="/dev/ttyS0"\nPRIVATE=kept\n')
            manifest = home / 'dwin-uart.json'
            manifest.write_text('{"port": "/dev/ttyS0"}')
            original = path.read_text()
            kconf = Configuration(ROOT, read_settings(home, original))
            kconf.syms['PETREL_DACAI'].set_value('y')  # as in menuconfig
            selected = collect(kconf)
            self.assertEqual(selected['PETREL_AUX_UART'], 'n')
            dwin = self.apply(home, original, selected, manifest)
            self.assertEqual(dwin.call_args.args[3:], (False, '/dev/ttyS0'))
            env = path.read_text()
            self.assertIn('PETREL_DACAI=1\n', env)
            self.assertIn('PETREL_AUX_UART=0\n', env)
            self.assertIn('PRIVATE=kept\n', env)

    def test_explicit_config_with_both_options_is_refused(self):
        import sys
        from tools import configure
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            values = configure.defaults(home)
            values.update(PETREL_AXIS_TRAVEL='n', PETREL_DACAI='y', PETREL_AUX_UART='y')
            selection = home / 'selection.config'
            selection.write_text(configure.config_text(values))
            argv = ['configure.py', '--home', str(home), '--user', 'user',
                    '--apply-config', str(selection), '--no-restart']
            with patch.object(sys, 'argv', argv), patch('sys.stderr') as stderr, \
                    patch.object(configure, 'apply') as applied:
                with self.assertRaises(SystemExit) as raised:
                    configure.main()
            self.assertEqual(raised.exception.code, 1)
            self.assertIn('auxiliary UART', ''.join(c.args[0] for c in stderr.write.call_args_list))
            applied.assert_not_called()
            self.assertFalse((home / '.config/Petrel/Petrel.env').exists())

    def test_installer_refuses_dacai_with_auxiliary_uart(self):
        script = (ROOT / 'install.sh').read_text()
        check = script.index('PETREL_DACAI)" == 1')
        self.assertLess(check, script.index('apt-get'))
        self.assertLess(check, script.index('dwin_uart_install.py'))


if __name__ == '__main__':
    unittest.main()
