import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.axis_travel_install import install, EXCLUDE, BEGIN, atomic

ROOT=Path(__file__).resolve().parents[1]


class AxisTravelInstallationTests(unittest.TestCase):
    def fixture(self, folder):
        home=Path(folder);klipper=home/'klipper'
        extras=klipper/'klippy/extras';extras.mkdir(parents=True)
        (extras/'existing.py').write_text('# original\n')
        subprocess.run(['git','init','-q',str(klipper)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(klipper),'add','.'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(klipper),'-c','user.name=CI','-c','user.email=ci@example.com',
                        'commit','-qm','fixture'],check=True,capture_output=True)
        config=home/'printer_data/config/printer.cfg';config.parent.mkdir(parents=True)
        config.write_text('[printer]\nkinematics: cartesian\n#*# SAVE_CONFIG\n');config.chmod(0o640)
        manifest=home/'.config/Petrel/axis-travel-install.json'
        return dict(repo=ROOT,klipper=klipper,printer_config=config,manifest=manifest)

    def test_enable_repeat_disable_keeps_git_clean_and_original_config(self):
        with tempfile.TemporaryDirectory() as folder:
            args=self.fixture(folder);config=args['printer_config'];original=config.read_bytes()
            self.assertTrue(install(True,**args));self.assertFalse(install(True,**args))
            target=args['klipper']/'klippy/extras/petrel_axis_travel.py'
            self.assertTrue(target.is_symlink())
            status=subprocess.check_output(['git','-C',str(args['klipper']),'status','--porcelain'],text=True)
            self.assertEqual(status,'')
            self.assertEqual(config.read_text().count(BEGIN),1)
            self.assertTrue(install(False,**args));self.assertFalse(install(False,**args))
            self.assertFalse(target.exists());self.assertEqual(config.read_bytes(),original)
            self.assertEqual(config.stat().st_mode & 0o777,0o640)

    def test_foreign_file_is_not_overwritten_and_disable_preserves_existing_exclude(self):
        with tempfile.TemporaryDirectory() as folder:
            args=self.fixture(folder);target=args['klipper']/'klippy/extras/petrel_axis_travel.py'
            target.write_text('foreign')
            with self.assertRaises(ValueError): install(True,**args)
            self.assertEqual(target.read_text(),'foreign');target.unlink()
            excluded=args['klipper']/'.git/info/exclude'
            excluded.write_text('# user rule\n'+EXCLUDE+'\n')
            install(True,**args);install(False,**args)
            self.assertEqual(excluded.read_text(),'# user rule\n'+EXCLUDE+'\n')

    def test_failure_rolls_back_symlink_config_and_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            args=self.fixture(folder);original=args['printer_config'].read_bytes()
            def fail(path,text):
                if path==args['manifest']: raise OSError('injected failure')
                return atomic(path,text)
            with patch('tools.axis_travel_install.atomic',side_effect=fail):
                with self.assertRaises(OSError): install(True,**args)
            self.assertEqual(args['printer_config'].read_bytes(),original)
            self.assertFalse((args['klipper']/'klippy/extras/petrel_axis_travel.py').exists())
            self.assertFalse((args['printer_config'].parent/'petrel-axis-travel.cfg').exists())
            self.assertEqual(args['printer_config'].stat().st_mode & 0o777,0o640)

    def test_existing_wildcard_include_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            args=self.fixture(folder);config=args['printer_config']
            original='[include *.cfg]\n'+config.read_text();config.write_text(original)
            install(True,**args)
            self.assertEqual(config.read_text(),original)
            install(False,**args)
            self.assertEqual(config.read_text(),original)

    def test_existing_configurator_defaults_on_then_preserves_explicit_off(self):
        from tools.configure import apply, read_settings
        with tempfile.TemporaryDirectory() as folder:
            args = self.fixture(folder)
            home = Path(folder)
            env_file = home / '.config/Petrel/Petrel.env'
            def configure(enabled=None):
                original = env_file.read_text() if env_file.exists() else ''
                values = read_settings(home, original)
                if enabled is not None:
                    values['PETREL_AXIS_TRAVEL'] = enabled
                apply(values, repo=ROOT, home=home, user='user', original=original,
                      dwin_manifest=home / 'no-dwin-manifest')
            configure()
            self.assertEqual(read_settings(home, env_file.read_text())['PETREL_AXIS_TRAVEL'], 'y')
            configure('n')
            self.assertEqual(read_settings(home, env_file.read_text())['PETREL_AXIS_TRAVEL'], 'n')
            configure()
            self.assertEqual(env_file.read_text().count('PETREL_AXIS_TRAVEL='), 1)
            self.assertNotIn(BEGIN, args['printer_config'].read_text())
