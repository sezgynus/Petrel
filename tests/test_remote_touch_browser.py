"""CI-only execution of the real Remote Display browser gesture handlers."""

from pathlib import Path
import shutil
import subprocess
import unittest
from dwin_emulator.remote import PAGE

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node runtime required for browser event harness")
class RemoteBrowserGestureTests(unittest.TestCase):
    def test_mobile_touch_and_pointer_gestures_dispatch_correct_hold_edges(self):
        process = subprocess.run(
            [shutil.which("node"), str(ROOT / "tools/test_remote_touch_browser.js")],
            input=PAGE, text=True, capture_output=True, timeout=10,
            check=False,
        )
        self.assertEqual(process.returncode, 0,
                         process.stdout + "\n" + process.stderr)
        self.assertIn("gesture contracts OK", process.stdout)


if __name__ == "__main__":
    unittest.main()
