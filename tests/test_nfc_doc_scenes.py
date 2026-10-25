"""NFC scenes exercise the production drawing path in CI, without hardware."""
import unittest
from tools import render_docs_screenshots as renderer
from tools.nfc_doc_scenes import SPECS


class NFCDocumentationTests(unittest.TestCase):
    def test_required_scenes_render_through_the_real_ui(self):
        required = {item[0] for item in SPECS}
        scenes = [item for item in renderer.SCENES if item[1] == 'nfc']
        self.assertEqual({item[0] for item in scenes}, required)
        self.assertEqual(len(scenes), 25)
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

    def test_reader_examples_keep_configuration_and_visible_connection_results(self):
        from unittest.mock import Mock
        from tools.nfc_doc_scenes import register
        captured = []
        def canvas():
            view = renderer.canvas()
            view.lcd.draw_text = Mock(wraps=view.lcd.draw_text)
            captured.append(view)
            return view
        registered = {}
        def scene(name, *labels):
            return lambda draw: registered.setdefault(name, draw)
        register(scene, canvas, renderer.finish)
        for name, result in (('nfc-settings-enabled', None), ('nfc-settings-port', None),
                             ('nfc-test-wait', 'Wait'), ('nfc-test-ok', 'OK'),
                             ('nfc-test-fail', 'Fail')):
            with self.subTest(scene=name):
                registered[name]()
                view = captured[-1]
                self.assertEqual(view._nfc_config().port, '/dev/ttyUSB0')
                self.assertTrue(all(view._nfc_confirmed.values()))
                if result:
                    self.assertEqual(view._nfc_test_values, view._nfc_config())
                    drawn = [str(call.args[-1]).strip()
                             for call in view.lcd.draw_text.call_args_list]
                    self.assertIn(result, drawn)
