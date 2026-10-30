from petrel.artwork.resources import ICON_LIBRARY_ID
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from petrel.emulator.assets import PanelAssets
from petrel.artwork.resources import SPOOL_LEFT_FLANGES, SPOOL_RIGHT_FLANGES
from petrel.features.spoolman.spool_view import SpoolView

ROOT = Path(__file__).resolve().parents[1]


class NativeCustomIconTests(unittest.TestCase):
    def test_custom_icon_dimensions_and_all_spool_sizes_stay_in_bounds(self):
        assets = PanelAssets()
        expected = {98: (110, 100), 99: (110, 100), 100: (20, 18),
                    101: (20, 20), 102: (20, 20), 103: (20, 20),
                    54: (20, 20), 55: (20, 20), 56: (110, 100), 57: (110, 100), 65: (42, 52)}
        for icon, size in expected.items():
            self.assertEqual(assets.icon(ICON_LIBRARY_ID, icon).size, size)
        for width in range(1, 43):
            lcd = Mock()
            spool = SpoolView(lcd, 80, 60, width, label_width=width)
            spool.draw()
            for call in lcd.show_icon.call_args_list:
                library, icon, x, y = call.args
                self.assertEqual(library, ICON_LIBRARY_ID)
                iw, ih = assets.icon(library, icon).size
                self.assertGreaterEqual(x, 80)
                self.assertLessEqual(x + iw, 80 + width)
                self.assertEqual((y, ih), (60, 52))

    def test_production_ui_no_longer_calls_atlas_renderers(self):
        for path in (ROOT / 'petrel').rglob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, ("draw_atlas_icon", "draw_atlas_icon_strip"), path.name)

    def test_flange_images_have_only_the_needed_width(self):
        assets = PanelAssets()
        for width in range(1, 8):
            for mapping in (SPOOL_LEFT_FLANGES, SPOOL_RIGHT_FLANGES):
                self.assertEqual(assets.icon(ICON_LIBRARY_ID, mapping[width]).size, (width, 52))

