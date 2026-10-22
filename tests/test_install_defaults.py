import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.env_defaults import ensure_emulator_default, ensure_nfc_default

ROOT = Path(__file__).resolve().parents[1]


class InstallerDefaultsTests(unittest.TestCase):
    def test_existing_config_gets_nfc_disabled_by_default_without_resetting_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'app.env'
            path.write_text('MOONRAKER_URL=http://localhost:7125')
            self.assertTrue(ensure_nfc_default(path))
            self.assertTrue(path.read_text().endswith('PETREL_NFC=0\n'))
            self.assertFalse(ensure_nfc_default(path))
            path.write_text('PETREL_NFC=1\n')
            self.assertFalse(ensure_nfc_default(path))
            self.assertEqual(path.read_text(), 'PETREL_NFC=1\n')

    def test_existing_config_adds_default_once_and_preserves_enabled_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'app.env'
            for content in ('MOONRAKER_URL=http://localhost:7125',
                            'MOONRAKER_URL=http://localhost:7125\n'):
                path.write_text(content); path.chmod(0o600)
                self.assertTrue(ensure_emulator_default(path))
                self.assertTrue(path.read_text().startswith(content))
                self.assertFalse(ensure_emulator_default(path))
                self.assertEqual(path.read_text().count('PETREL_EMULATOR='), 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text('PETREL_EMULATOR=1\n')
            self.assertFalse(ensure_emulator_default(path))
            self.assertEqual(path.read_text(), 'PETREL_EMULATOR=1\n')

    def test_configurator_writes_off_and_preserves_existing_enabled_value(self):
        from tools.configure import apply, read_settings
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/Petrel/Petrel.env'
            def configure(enabled=None):
                original = path.read_text() if path.exists() else ''
                values = read_settings(home, original)
                values['PETREL_AXIS_TRAVEL'] = 'n'
                if enabled is not None:
                    values['PETREL_EMULATOR'] = values['PETREL_REMOTE'] = enabled
                apply(values, repo=ROOT, home=home, user='user', original=original,
                      dwin_manifest=home / 'no-dwin-manifest')
            configure()
            for key in ('PETREL_EMULATOR', 'PETREL_REMOTE'):
                self.assertEqual(read_settings(home, path.read_text())[key], 'n')
            configure('y')
            configure()
            for key in ('PETREL_EMULATOR', 'PETREL_REMOTE'):
                self.assertEqual(read_settings(home, path.read_text())[key], 'y')
            configure('n')
            for key in ('PETREL_EMULATOR', 'PETREL_REMOTE'):
                self.assertEqual(read_settings(home, path.read_text())[key], 'n')
                self.assertEqual(path.read_text().count(key + '='), 1)

    def test_configurator_preserves_custom_settings_and_literal_values(self):
        from tools.configure import apply, read_settings
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/Petrel/Petrel.env'
            path.parent.mkdir(parents=True)
            literal = '$(touch ' + str(home / 'unexpected-evaluation') + ')'
            custom = [
                'PETREL_EMULATOR_FONT="/tmp/custom font.HZK"',
                'PETREL_EMULATOR_SOCKET=/tmp/custom-capture.sock',
                'PETREL_SCREENSHOT_DIRECTORY=/tmp/custom-shots',
                'FUTURE_OPTION=' + literal,
                'MOONRAKER_API_KEY="private literal $value"',
            ]
            path.write_text('PETREL_EMULATOR=1\nPETREL_REMOTE=true\n'
                            'PETREL_SETTINGS_FILE="/tmp/custom presets.json"\n'
                            'PETREL_REMOTE_HOST=127.0.0.1\nPETREL_REMOTE_PORT=8099\n'
                            + '\n'.join(custom) + '\n')
            for _ in range(2):
                original = path.read_text()
                values = read_settings(home, original)
                values['PETREL_AXIS_TRAVEL'] = 'n'
                apply(values, repo=ROOT, home=home, user='user', original=original,
                      dwin_manifest=home / 'no-dwin-manifest')
                for line in custom:
                    self.assertEqual(path.read_text().splitlines().count(line), 1)
                saved = read_settings(home, path.read_text())
                self.assertEqual(saved['PETREL_SETTINGS_FILE'], '/tmp/custom presets.json')
                self.assertEqual(saved['PETREL_REMOTE_HOST'], '127.0.0.1')
                self.assertEqual(saved['PETREL_REMOTE_PORT'], '8099')
                self.assertEqual(saved['PETREL_EMULATOR'], 'y')
                self.assertEqual(saved['PETREL_REMOTE'], 'y')
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertFalse((home / 'unexpected-evaluation').exists())
