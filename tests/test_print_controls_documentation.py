"""Exercise both documented CLI paths, including actual recovery navigation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


class PrintControlsDocumentationTests(unittest.TestCase):
    def test_native_and_framed_commands_finish_with_multiframe_gifs(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            for framed, size in ((False, (272, 480)), (True, (528, 900))):
                with self.subTest(framed=framed):
                    target = Path(directory) / ('framed.gif' if framed else 'native.gif')
                    command = [sys.executable, str(root / 'tools/render_print_controls.py'),
                               '--output', str(target)]
                    if framed:
                        command.append('--frame')
                    result = subprocess.run(command, cwd=root, capture_output=True,
                                            text=True, timeout=120)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    with Image.open(target) as image:
                        self.assertEqual(image.size, size)
                        self.assertGreater(image.n_frames, 10)
                        for frame in range(image.n_frames):
                            image.seek(frame)
                            image.load()
