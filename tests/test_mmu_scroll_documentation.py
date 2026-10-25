"""The documented MMU-scroll example must use Back and finish on Print."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from tools import render_docs_workflows as workflows


class MMUScrollDocumentationTests(unittest.TestCase):
    def test_real_encoder_back_route_never_opens_recovery_and_finishes_on_print(self):
        captured = []
        original = workflows.workflow_view
        def view(kind):
            result = original(kind)
            result.Enter_MMU_Menu = Mock(side_effect=AssertionError('Back must not open recovery'))
            captured.append(result)
            return result
        with patch.object(time, 'strftime', return_value='12:34'), \
                patch.object(time, 'monotonic', return_value=0), \
                patch.object(workflows, 'workflow_view', side_effect=view):
            frames, durations = workflows.mmu_error_scroll_frames()
        result = captured[-1]
        self.assertEqual(result.checkkey, result.PrintProcess)
        self.assertEqual(result._focus_error_choice, 1)
        self.assertEqual(result._focus_error_scroll, 0)
        result.Enter_MMU_Menu.assert_not_called()
        self.assertEqual(len(frames), len(durations))
        self.assertGreater(len(frames), 3)
        self.assertTrue(all(frame.size == (272, 480) for frame in frames))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs/assets').mkdir(parents=True)
            with patch.object(workflows, 'ROOT', root):
                workflows.save('mmu-error-scroll-demo.gif', frames, durations)
            for path, size in (
                    (root / 'docs/assets/mmu-error-scroll-demo.gif', (272, 480)),
                    (root / 'docs/assets/framed/mmu-error-scroll-demo.gif', (528, 900))):
                with self.subTest(path=path.name, size=size), Image.open(path) as image:
                    self.assertEqual(image.size, size)
                    self.assertGreater(image.n_frames, 3)
                    image.seek(image.n_frames - 1)
                    image.load()
