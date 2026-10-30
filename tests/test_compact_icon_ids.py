"""Dense managed IDs and safe same-slot migration from older ID directories."""
import hashlib
import json
from pathlib import Path
import zlib
from unittest import TestCase
from unittest.mock import Mock, patch

import petrel.artwork.icon_library as icons
from petrel.artwork.resources import ICON_LIBRARY_ID
from petrel.hardware.dwin.driver import T5UIC1Display
from tools.pack_icon_library import entries
import test_managed_icon_library as managed


class CompactIconIDs(TestCase):
    def legacy_record(self, hashes, version=b'PETICO04'):
        raw = bytearray(icons.metadata(hashes))
        raw[:8] = version
        raw[-4:] = zlib.crc32(raw[:-4]).to_bytes(4, 'big')
        return bytes(raw)

    def test_sources_and_export_have_dense_ids_with_unused_tail(self):
        root = Path(__file__).resolve().parents[1]
        source_ids = sorted(int(p.stem) for p in (root / 'assets/icons').glob('*.jpg'))
        self.assertEqual(source_ids, list(range(len(source_ids))))
        data = (root / 'assets/emulator/2.ICO').read_bytes()
        packed_ids = sorted(n for n, _, _, _ in entries(data))
        self.assertEqual(packed_ids, source_ids)
        record = json.loads((root / 'assets/icons/id-redundancy-cleanup.json').read_text())
        migration = record['mapping']
        physical = [v for k, v in migration.items() if k not in record['aliases']]
        self.assertEqual(len(set(physical)), len(physical))
        self.assertLessEqual(set(migration.values()), set(source_ids))
        self.assertEqual(len(source_ids), 186)
        self.assertEqual(len(record["aliases"]), 12)
        self.assertEqual(len(record["removed_ids"]), 2)
        for index in range(len(source_ids), 256):
            self.assertFalse(any(data[index*16:(index+1)*16]))

    def test_dashboard_and_move_menu_share_identical_axis_ids(self):
        from test_regressions import ui
        PetrelDisplay = ui.PetrelDisplay
        self.assertEqual((PetrelDisplay.ICON_MaxSpeedX, PetrelDisplay.ICON_MaxSpeedY,
                          PetrelDisplay.ICON_MaxSpeedZ),
                         (PetrelDisplay.ICON_MoveX, PetrelDisplay.ICON_MoveY,
                          PetrelDisplay.ICON_MoveZ))

    def test_old_id_meanings_cannot_start_new_boot_frames_before_upload(self):
        display = object.__new__(T5UIC1Display)
        hashes = [b'x' * 32]
        display.read_flash = Mock(return_value=self.legacy_record(hashes))
        self.assertIsNone(display._startup_animation_library())
        display.read_flash.return_value = icons.metadata(hashes)
        self.assertEqual(display._startup_animation_library(), ICON_LIBRARY_ID)
        display.read_flash.return_value = icons.metadata([bytes(32)])
        self.assertIsNone(display._startup_animation_library())

    def test_migrating_boot_uses_no_resident_icons_until_directory_commit(self):
        from test_boot_splash import BootSplashTests
        view = BootSplashTests().view()
        view.lcd._boot_animation_library = None
        view._draw_boot_progress(40)
        self.assertFalse(any(frame[1] in (0x23, 0x28) for frame in view.lcd.serial.frames))
        view.lcd.serial.frames.clear()
        view.lcd._boot_animation_library = ICON_LIBRARY_ID
        view._draw_boot_progress(70)
        self.assertTrue(any(frame[1] == 0x23 for frame in view.lcd.serial.frames))
        self.assertTrue(any(frame[1] == 0x28 for frame in view.lcd.serial.frames))

    @patch('petrel.artwork.icon_library.time.sleep')
    def test_older_same_slot_hashes_force_upload_then_current_reconnect_is_unchanged(self, _):
        icons._ATTEMPTS.clear()
        self.addCleanup(icons._ATTEMPTS.clear)
        data = icons.pack_records([(1, 20, 20, b'x'*30000), (2, 20, 20, b'y'*1000)])
        hashes = [hashlib.sha256(data[i:i+icons.BLOCK_SIZE]).digest()
                  for i in range(0, len(data), icons.BLOCK_SIZE)]
        lcd, memory = managed.ManagedIconTests().panel()
        memory[icons.METADATA_ADDRESS:icons.METADATA_ADDRESS+icons.METADATA_SIZE] = self.legacy_record(hashes)
        untouched = bytes(memory[:icons.METADATA_ADDRESS])
        with patch('petrel.artwork.icon_library.build_library', return_value=data):
            self.assertTrue(icons.sync_library(lcd))
            self.assertEqual([c.args[0] for c in lcd.store_sram_as_picture.call_args_list],
                             [ICON_LIBRARY_ID+1, ICON_LIBRARY_ID])
            calls = [c[0] for c in lcd.mock_calls]
            self.assertLess(calls.index('set_animation_mask'), calls.index('write_sram'))
            self.assertEqual(bytes(memory[:icons.METADATA_ADDRESS]), untouched)
            lcd.reset_mock()
            self.assertFalse(icons.sync_library(lcd))
            lcd.store_sram_as_picture.assert_not_called()
            lcd.write_flash.assert_not_called()
