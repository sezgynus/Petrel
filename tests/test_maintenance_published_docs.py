"""Published Maintenance guides and pictures stay paired with the real UI."""
from pathlib import Path
import os
import time
import unittest
from unittest.mock import patch
from PIL import Image,ImageChops
from tools import render_docs_screenshots as renderer

ROOT=Path(__file__).resolve().parents[1]

class PublishedMaintenanceGuide(unittest.TestCase):
    def scenes(self):
        return [s for s in renderer.SCENES if s[1]=='maintenance']

    def test_both_guides_and_galleries_include_every_current_scene(self):
        self.assertEqual(len(self.scenes()),24)
        for tr in (False,True):
            suffix='_TR' if tr else ''
            guide=(ROOT/('docs/user-guide'+suffix+'.md')).read_text(encoding='utf-8')
            gallery=(ROOT/('docs/screenshots'+suffix+'.md')).read_text(encoding='utf-8')
            self.assertNotIn('Maintenance placeholder',gallery)
            self.assertNotIn('four Graphite tiles',guide)
            self.assertNotIn('dört Graphite kutucuk',guide)
            for name,*_ in self.scenes():
                self.assertIn('assets/screens/framed/'+name+'.png',guide)
                self.assertIn('assets/screens/framed/'+name+'.png',gallery)
                self.assertIn('assets/screens/'+name+'.png',gallery)
            for label in ('Care schedule','Check printer','Diagnostics','Recommendations','Back'):
                self.assertIn(label,guide)

    @patch('t5uic1_driver.time.sleep')
    def test_scrolled_host_scene_moves_only_report_content(self,_):
        with patch.object(time,'strftime',return_value='12:34'), \
                patch.object(time,'monotonic',return_value=3.6):
            scenes={scene[0]:scene[-1] for scene in self.scenes()}
            top=scenes['maintenance-host']()
            scrolled=scenes['maintenance-host-page-2']()
        self.assertIsNone(ImageChops.difference(top.crop((0,0,272,148)),scrolled.crop((0,0,272,148))).getbbox())
        self.assertIsNone(ImageChops.difference(top.crop((0,360,272,480)),scrolled.crop((0,360,272,480))).getbbox())
        self.assertIsNotNone(ImageChops.difference(top.crop((0,148,260,340)),scrolled.crop((0,148,260,340))).getbbox())

    # Published pixels are intentionally refreshed by manual Documentation Render,
    # not by every source push. Verify only after that workflow regenerates them.
    @unittest.skipUnless(os.environ.get('PETREL_VERIFY_PUBLISHED_SCREENS') == '1',
                         'Published pixels are checked by manual Documentation Render')
    @patch('t5uic1_driver.time.sleep')
    def test_published_native_pixels_match_the_current_production_ui(self,_):
        with patch.object(time,'strftime',return_value='12:34'),patch('mmu_filament_view.time.monotonic',return_value=3.6):
            for name,group,en,tr,draw in self.scenes():
                with self.subTest(scene=name),Image.open(ROOT/('docs/assets/screens/'+name+'.png')) as published:
                    actual=draw()
                    self.assertEqual(published.size,(272,480))
                    self.assertEqual(published.mode,'RGB')
                    self.assertIsNone(ImageChops.difference(published,actual).getbbox())

    def test_every_presentation_frame_contains_exact_native_panel_pixels(self):
        for name,*_ in self.scenes():
            native=ROOT/('docs/assets/screens/'+name+'.png')
            framed=ROOT/('docs/assets/screens/framed/'+name+'.png')
            # A newly registered scene precedes its explicit CI screenshot
            # publication. The manual renderer verifies all scenes and pixels
            # before publishing both sizes.
            if not native.is_file() or not framed.is_file():
                self.assertNotEqual(os.environ.get('PETREL_VERIFY_PUBLISHED_SCREENS'),'1')
                continue
            with self.subTest(scene=name),Image.open(native) as panel,Image.open(framed) as frame:
                self.assertIsNone(ImageChops.difference(panel,frame.convert('RGB').crop((128,122,400,602))).getbbox())
