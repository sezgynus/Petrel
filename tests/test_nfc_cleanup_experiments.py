"""Safe cleanup of only obsolete PN532 libraries and experiment markers."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.cleanup_nfc_experiments import cleanup, paths


class CleanupPN532ExperimentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data' / 'Petrel'
        self.config = self.root / 'config' / 'Petrel'
        self.data.mkdir(parents=True)
        self.config.mkdir(parents=True)

    def test_only_experiment_artifacts_removed_with_dry_run_first(self):
        old = self.data / 'libnfc-pn532-modedet05'
        old.mkdir()
        (old / 'libnfc.so.6').write_bytes(b'test')
        build = self.data / '.pn532-picc-build.mock'
        build.mkdir()
        profile = self.config / 'nfc-target-experiment.json'
        profile.write_text('{"profile":"A"}')
        enable = self.config / 'nfc-target-system-modedet.enabled'
        enable.write_text('enabled-v1')
        keep = self.config / 'nfc-settings.json'
        keep.write_text('user settings')
        unrelated = self.data / 'important-data'
        unrelated.mkdir()
        with patch('tools.cleanup_nfc_experiments.validate_production'):
            self.assertEqual(cleanup(self.data, self.config), 4)
            self.assertTrue(old.exists())
            self.assertEqual(cleanup(self.data, self.config, apply=True), 4)
        self.assertFalse(old.exists())
        self.assertFalse(build.exists())
        self.assertFalse(profile.exists())
        self.assertFalse(enable.exists())
        self.assertEqual(keep.read_text(), 'user settings')
        self.assertTrue(unrelated.exists())
        self.assertEqual(paths(self.data, self.config), ())

    def test_refuse_symlinked_parent_even_in_dry_run(self):
        data_link = self.root / 'symlink-data'
        data_link.symlink_to(self.data, target_is_directory=True)
        with patch('tools.cleanup_nfc_experiments.validate_production'):
            with self.assertRaisesRegex(RuntimeError, 'symlinked'):
                cleanup(data_link, self.config, apply=False)
            with self.assertRaisesRegex(RuntimeError, 'symlinked'):
                cleanup(data_link, self.config, apply=True)

    def test_script_direct_invocation_resolves_project_imports(self):
        # Test the exact command documented for Raspberry Pi, not imports
        # from the unittest runner's project-root sys.path.
        script = Path(__file__).resolve().parents[1] / 'tools' / 'cleanup_nfc_experiments.py'
        marker = self.config / 'nfc-target-system-modedet.enabled'
        marker.write_text('experimental')
        env = os.environ.copy()
        env['XDG_DATA_HOME'] = str(self.data.parent)
        env['XDG_CONFIG_HOME'] = str(self.config.parent)
        env.pop('PYTHONPATH', None)
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Would remove:', result.stdout)
        self.assertTrue(marker.exists(), 'Dry run must not delete marker')

    def test_guard_prevents_removing_any_files(self):
        marker = self.config / 'nfc-target-modedet.enabled'
        marker.write_text('old')
        with patch('tools.cleanup_nfc_experiments.validate_production',
                   side_effect=RuntimeError('unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                cleanup(self.data, self.config, apply=True)
        self.assertTrue(marker.exists())
