import json
from pathlib import Path
import tempfile
import unittest

from tools.nfc_install import install


class NFCInstallTests(unittest.TestCase):
    def test_installs_runtime_package_and_removes_only_petrel_owned_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'nfc.json'
            installed = False
            calls = []

            def execute(*args, check=True):
                nonlocal installed
                calls.append(args)
                if args[0] == 'dpkg-query':
                    return type('Result', (), {
                        'returncode': 0 if installed else 1,
                        'stdout': 'installed' if installed else '',
                    })()
                if args[:3] == ('apt-get', 'install', '-y'):
                    installed = True
                elif args[:3] == ('apt-get', 'remove', '-y'):
                    installed = False
                return type('Result', (), {'returncode': 0, 'stdout': ''})()

            install(True, manifest=manifest, execute=execute)
            self.assertTrue(installed)
            self.assertEqual(json.loads(manifest.read_text()), {
                'enabled': True, 'package': 'libnfc6', 'installed_by_petrel': True})
            self.assertIn(('apt-get', 'update'), calls)
            self.assertIn(('apt-get', 'install', '-y', 'libnfc6'), calls)

            calls.clear()
            install(False, manifest=manifest, execute=execute)
            self.assertFalse(installed)
            self.assertFalse(manifest.exists())
            self.assertIn(('apt-get', 'remove', '-y', 'libnfc6'), calls)

    def test_preserves_a_libnfc_package_that_existed_before_petrel_enabled_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'nfc.json'
            installed = True
            calls = []

            def execute(*args, check=True):
                calls.append(args)
                return type('Result', (), {'returncode': 0, 'stdout': 'installed'})()

            install(True, manifest=manifest, execute=execute)
            self.assertFalse(json.loads(manifest.read_text())['installed_by_petrel'])
            install(False, manifest=manifest, execute=execute)
            self.assertFalse(any(call[:2] == ('apt-get', 'remove') for call in calls))
            self.assertFalse(manifest.exists())


if __name__ == '__main__':
    unittest.main()
