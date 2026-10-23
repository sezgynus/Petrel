"""Reversible managed virtual buzzer extra wiring and coexistence."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from tools.klipper_buzzer_install import install, BEGIN, EXCLUDE
from tools.configure import defaults, Configuration, collect

ROOT = Path(__file__).resolve().parents[1]


class VirtualBuzzerInstallTests(unittest.TestCase):
    def fixture(self, folder):
        home = Path(folder)
        klipper = home / 'klipper'
        (klipper / 'klippy/extras').mkdir(parents=True)
        (klipper / '.git/info').mkdir(parents=True)
        (klipper / '.git/info/exclude').write_text('foreign-entry\n')
        cfg = home / 'printer_data/config/printer.cfg'
        cfg.parent.mkdir(parents=True)
        cfg.write_text('[printer]\nkinematics: cartesian\n')
        # Simplify git queries while exercising real file writes/rollbacks.
        def command(*args, **kwargs):
            if 'ls-files' in args[0]:
                return type('R', (), {'returncode': 1})()
            return '.git/info/exclude'
        return dict(repo=ROOT, klipper=klipper, printer_config=cfg,
                    manifest=home/'.config/Petrel/klipper-buzzer-install.json',
                    home=home), command

    def test_enable_disable_keeps_opaque_cfg_and_user_exclude(self):
        with tempfile.TemporaryDirectory() as folder:
            args, command = self.fixture(folder)
            original = args['printer_config'].read_text()
            with patch('tools.klipper_buzzer_install.subprocess.run', side_effect=command), (
                    patch('tools.klipper_buzzer_install.subprocess.check_output',
                          return_value='.git/info/exclude')):
                self.assertTrue(install(True, **args))
                self.assertFalse(install(True, **args))
                content = args['printer_config'].read_text()
                self.assertEqual(content.count(BEGIN), 1)
                fragment = args['printer_config'].parent / 'petrel-buzzer.cfg'
                self.assertIn('[petrel_buzzer Buzzer]', fragment.read_text())
                self.assertIn('socket_path:', fragment.read_text())
                self.assertTrue((args['klipper'] / 'klippy/extras/petrel_buzzer.py').is_symlink())
                self.assertTrue(install(False, **args))
                self.assertEqual(args['printer_config'].read_text(), original)
                self.assertFalse(fragment.exists())
                self.assertFalse((args['klipper'] / 'klippy/extras/petrel_buzzer.py').exists())
                self.assertEqual((args['klipper'] / '.git/info/exclude').read_text(), 'foreign-entry\n')

    def test_foreign_extra_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            args, command = self.fixture(folder)
            (args['klipper'] / 'klippy/extras/petrel_buzzer.py').write_text('# foreign\n')
            with patch('tools.klipper_buzzer_install.subprocess.run', side_effect=command):
                with self.assertRaisesRegex(ValueError, 'foreign'):
                    install(True, **args)


if __name__ == '__main__':
    unittest.main()
