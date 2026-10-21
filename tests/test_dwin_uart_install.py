import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from tools.dwin_uart_install import Installer, OWNED, MANIFEST, DROPIN, SERVICE, source_version, quote
from tools.env_defaults import ensure_aux_uart_default

ROOT = Path(__file__).resolve().parents[1]


class InstallationContracts(unittest.TestCase):
    def fixture(self, root):
        active = {'Petrel.service'}
        calls = []
        fail = []
        def execute(*args, check=True):
            calls.append(args)
            if fail and args == fail[0]:
                fail.clear()
                raise subprocess.CalledProcessError(1, args)
            result = subprocess.CompletedProcess(args, 0, '', '')
            if args[:2] == ('systemctl', 'is-active'):
                result.returncode = 0 if args[-1] in active else 3
            elif args[:2] == ('systemctl', 'is-enabled'):
                result.returncode = 1
            elif args[:2] == ('systemctl', 'stop'):
                active.discard(args[-1])
            elif args[:2] in (('systemctl', 'start'), ('systemctl', 'enable')):
                active.add(args[-1])
            elif args == ('modprobe', 'dwin_uart'):
                (root / 'dev').mkdir(exist_ok=True)
                (root / 'dev/ttyDWIN0').touch()
                (root / 'sys/module/dwin_uart').mkdir(parents=True, exist_ok=True)
            elif args == ('modprobe', '-r', 'dwin_uart'):
                (root / 'dev/ttyDWIN0').unlink(missing_ok=True)
                module = root / 'sys/module/dwin_uart'
                if module.exists():
                    module.rmdir()
            return result
        builder = Mock()
        installer = Installer(root, execute, busy=Mock(return_value=[]), builder=builder)
        return installer, active, calls, fail, builder

    def apply(self, installer, enabled):
        installer.apply(enabled, ROOT, Path('/home/printer'), 'printer', '/dev/ttyAMA0')

    def test_enable_repeat_disable_and_reinstall_preserve_direct_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installer, active, calls, fail, builder = self.fixture(root)
            self.apply(installer, True)
            self.assertTrue(all(installer.path(p).exists() for p in OWNED))
            self.assertIn('PETREL_DWIN_SOCKET=', installer.path(DROPIN).read_text())
            self.assertEqual(json.loads(installer.path(MANIFEST).read_text())['version'], source_version(ROOT))
            self.assertIn('Petrel.service', active)
            calls.clear()
            installer.busy.return_value = [123]
            self.apply(installer, True)  # No-op is safe even while the TTY is open.
            self.assertFalse(any(c[:2] == ('systemctl', 'stop') for c in calls))
            self.assertEqual(builder.call_count, 1)
            installer.busy.return_value = []
            self.apply(installer, False)
            self.assertFalse(any(installer.path(p).exists() for p in OWNED))
            self.assertIn('Petrel.service', active)
            self.assertNotIn(SERVICE, active)
            self.apply(installer, True)
            self.assertIn(SERVICE, active)

    def test_busy_port_prevents_removal_before_stopping_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            self.apply(installer, True)
            before = installer.path(MANIFEST).read_text()
            installer.busy.return_value = [42]
            calls.clear()
            with self.assertRaisesRegex(RuntimeError, '42'):
                self.apply(installer, False)
            self.assertFalse(calls)
            self.assertEqual(installer.path(MANIFEST).read_text(), before)
            self.assertIn(SERVICE, active)

    def test_missing_headers_or_build_failure_does_not_stop_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            builder.side_effect = RuntimeError('headers unavailable')
            with self.assertRaisesRegex(RuntimeError, 'headers'):
                self.apply(installer, True)
            self.assertFalse(any(c[:2] == ('systemctl', 'stop') for c in calls))
            self.assertIn('Petrel.service', active)
            self.assertFalse(installer.path(MANIFEST).exists())

    def test_failed_service_start_rolls_back_to_direct_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            fail.append(('systemctl', 'enable', '--now', SERVICE))
            with self.assertRaises(subprocess.CalledProcessError):
                self.apply(installer, True)
            self.assertFalse(any(installer.path(p).exists() for p in OWNED))
            self.assertIn('Petrel.service', active)
            self.assertNotIn(SERVICE, active)

    def test_failed_removal_restores_broker_and_its_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            self.apply(installer, True)
            before = {p: installer.path(p).read_text() for p in OWNED}
            version = source_version(ROOT)
            fail.append(('dkms', 'remove', '-m', 'petrel-dwin-uart', '-v', version, '--all'))
            with self.assertRaises(subprocess.CalledProcessError):
                self.apply(installer, False)
            self.assertEqual({p: installer.path(p).read_text() for p in OWNED}, before)
            self.assertIn(SERVICE, active)
            self.assertIn('Petrel.service', active)

    def test_defaults_are_opt_in_and_preserve_existing_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'app.env'
            path.write_text('CUSTOM=literal')
            path.chmod(0o600)
            self.assertTrue(ensure_aux_uart_default(path))
            self.assertEqual(path.read_text(), 'CUSTOM=literal\nPETREL_AUX_UART=0\n')
            self.assertFalse(ensure_aux_uart_default(path))
            path.write_text('PETREL_AUX_UART=1\n')
            self.assertFalse(ensure_aux_uart_default(path))
            self.assertEqual(path.read_text(), 'PETREL_AUX_UART=1\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_systemd_arguments_escape_specifiers_and_reject_newlines(self):
        self.assertEqual(quote('/tmp/with space%/a"b'), '"/tmp/with space%%/a\\"b"')
        with self.assertRaises(ValueError):
            quote('/dev/ttyAMA0\nExecStart=bad')


if __name__ == '__main__':
    unittest.main()
