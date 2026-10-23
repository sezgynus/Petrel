from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, Mock
import hashlib
import zlib
import icon_library as icons
from lcd_resources import ICON_LIBRARY_ID, ICON_LIBRARY_FILENAME
import test_managed_icon_library as managed
from tools.pack_icon_library import entries, validate_block_layout


class LibraryMigrationTests(TestCase):
    def setUp(self):
        icons._ATTEMPTS.clear()
        self.addCleanup(icons._ATTEMPTS.clear)

    def old_metadata(self, data, library):
        hashes = [hashlib.sha256(data[i:i + icons.BLOCK_SIZE]).digest()
                  for i in range(0, len(data), icons.BLOCK_SIZE)]
        body = (icons.MAGIC + bytes((library, len(hashes))) + b''.join(hashes)).ljust(508, bytes(1))
        return body + zlib.crc32(body).to_bytes(4, 'big')

    @patch('icon_library.time.sleep')
    def test_legacy_hashes_cannot_skip_relocation_and_animations_stop_before_writes(self, _):
        data = icons.pack_records([(1, 20, 20, b'x' * 30000), (2, 20, 20, b'y' * 1000)])
        for old_library in (3, 7):
            with self.subTest(old_library=old_library):
                lcd, memory = managed.ManagedIconTests().panel()
                old = self.old_metadata(data, old_library)
                memory[icons.METADATA_ADDRESS:icons.METADATA_ADDRESS + icons.METADATA_SIZE] = old
                untouched = bytes(memory[:icons.METADATA_ADDRESS])
                with patch('icon_library.build_library', return_value=data):
                    self.assertTrue(icons.sync_library(lcd))
                    self.assertEqual([c.args[0] for c in lcd.store_sram_as_picture.call_args_list], [3, 2])
                    names = [c[0] for c in lcd.mock_calls]
                    self.assertLess(names.index('set_animation_mask'), names.index('store_sram_as_picture'))
                    lcd.set_animation_mask.assert_called_once_with(0)
                    lcd.reset_mock()
                    self.assertFalse(icons.sync_library(lcd))
                    lcd.store_sram_as_picture.assert_not_called()
                self.assertEqual(bytes(memory[:icons.METADATA_ADDRESS]), untouched)
                self.assertEqual(memory[icons.METADATA_ADDRESS + 8], 2)

    @patch('icon_library.time.sleep')
    def test_interrupted_relocation_resumes_with_directory_last(self, _):
        data = icons.pack_records([(1, 20, 20, b'x' * 30000), (2, 20, 20, b'y' * 1000)])
        lcd, memory = managed.ManagedIconTests().panel()
        old = self.old_metadata(data, 3)
        memory[icons.METADATA_ADDRESS:icons.METADATA_ADDRESS + icons.METADATA_SIZE] = old
        lcd.store_sram_as_picture.side_effect = [None, TimeoutError('directory ACK lost')]
        with patch('icon_library.build_library', return_value=data):
            with self.assertRaises(TimeoutError):
                icons.sync_library(lcd)
            raw = bytes(memory[icons.METADATA_ADDRESS:icons.METADATA_ADDRESS + icons.METADATA_SIZE])
            self.assertEqual(raw[8], 2)
            self.assertEqual(icons.parse_metadata(raw)[0], bytes(32))
            icons._ATTEMPTS.clear()
            lcd.reset_mock(); lcd.store_sram_as_picture.side_effect = None
            self.assertTrue(icons.sync_library(lcd))
            self.assertEqual([c.args[0] for c in lcd.store_sram_as_picture.call_args_list], [2])

    def test_fourteenth_block_and_metadata_fit_without_touching_picture_zero_or_one(self):
        payload = bytes.fromhex('ffd8') + bytes(32763) + bytes.fromhex('ffd9')
        data = icons.pack_records([(i, 20, 20, payload) for i in range(13)])
        self.assertEqual((ICON_LIBRARY_ID, ICON_LIBRARY_FILENAME, icons.MAX_BLOCKS), (2, '2.ICO', 14))
        self.assertEqual(len(data), 14 * icons.BLOCK_SIZE)
        validate_block_layout(data, ICON_LIBRARY_ID)
        hashes = [hashlib.sha256(data[i:i + icons.BLOCK_SIZE]).digest()
                  for i in range(0, len(data), icons.BLOCK_SIZE)]
        raw = icons.metadata(hashes)
        self.assertEqual(len(raw), 512)
        self.assertEqual(icons.parse_metadata(raw), hashes)
        self.assertEqual(icons.METADATA_ADDRESS + len(raw), 0x0400)

    def test_export_cli_defaults_to_managed_slot(self):
        import tempfile
        from tools import pack_icon_library as tool
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / '2.ICO'
            with patch('sys.argv', ['pack_icon_library.py', str(icons.SOURCE_DIRECTORY), str(destination)]):
                tool.main()
            validate_block_layout(destination.read_bytes(), 2)

    def test_reference_export_moved_without_changing_any_jpeg_payload(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / 'assets/emulator/3.ICO').exists())
        data = (root / 'assets/emulator/2.ICO').read_bytes()
        self.assertEqual(data, icons.build_library())
        for index, entry, offset, payload in entries(data):
            self.assertEqual(payload, (root / f'assets/icons/{index:03d}.jpg').read_bytes())
