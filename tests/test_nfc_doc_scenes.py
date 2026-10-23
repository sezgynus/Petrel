"""NFC scenes exercise the production drawing path in CI, without hardware."""
import unittest
from tools import render_docs_screenshots as renderer
from tools.nfc_doc_scenes import SPECS


class NFCDocumentationTests(unittest.TestCase):
    def test_required_scenes_render_through_the_real_ui(self):
        required = {item[0] for item in SPECS}
        scenes = [item for item in renderer.SCENES if item[1] == 'nfc']
        self.assertEqual({item[0] for item in scenes}, required)
        self.assertEqual(len(scenes), 12)
        for name, _, english, turkish, draw in scenes:
            with self.subTest(scene=name):
                self.assertTrue(english)
                self.assertTrue(turkish)
                image = draw()
                self.assertEqual(image.size, (272, 480))
                self.assertEqual(image.mode, 'RGB')

    def test_gate_choice_scene_displays_real_assignable_gates(self):
        from unittest.mock import patch
        original = renderer.canvas
        captured = []
        def canvas(*args, **kwargs):
            view = original(*args, **kwargs)
            captured.append(view)
            return view
        with patch.object(renderer, 'canvas', side_effect=canvas):
            # Registration closes over canvas, so register a separate scene list.
            from tools.nfc_doc_scenes import register
            registered = {}
            def scene(name, *labels):
                return lambda draw: registered.setdefault(name, draw)
            register(scene, canvas, renderer.finish)
            registered['nfc-gate-choose']()
        popup = captured[-1]._nfc_gate_popup
        self.assertGreater(len(popup['operations']), 1)
        self.assertEqual(popup['spool'].id, 17)
        self.assertIsNone(popup['operation'])
