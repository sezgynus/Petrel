import json
import getpass
import shutil
import sys
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.dwin_uart_install import (Installer, OWNED, MANIFEST, DROPIN, SERVICE,
    source_version, quote, service_text, broker_binary, build_broker, valid_manifest,
    BROKER_DIRECTORY)
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
        def native_build(repo, build_root, execute):
            path = build_root / broker_binary(repo).lstrip('/')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'test executable')
            path.chmod(0o755)
        installer = Installer(root, execute, busy=Mock(return_value=[]), builder=builder,
                              broker_builder=Mock(side_effect=native_build))
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
            binary = installer.path(broker_binary(ROOT))
            self.assertTrue(binary.exists())
            self.assertIn(quote(broker_binary(ROOT)), installer.path('/etc/systemd/system/' + SERVICE).read_text())
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
            self.assertFalse(binary.exists())
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
            self.assertFalse(installer.path(broker_binary(ROOT)).exists())

    def test_native_build_failure_keeps_existing_python_transport_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            installer.broker_builder.side_effect = RuntimeError('native compilation failed')
            with self.assertRaisesRegex(RuntimeError, 'native compilation'):
                self.apply(installer, True)
            self.assertFalse(any(c[:2] == ('systemctl', 'stop') for c in calls))
            self.assertIn('Petrel.service', active)
            self.assertFalse(installer.path(MANIFEST).exists())

    def test_unprivileged_exec_failure_does_not_stop_running_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            fail.append(('runuser', '-u', 'printer', '--',
                         str(installer.path(broker_binary(ROOT))), '--help'))
            with self.assertRaises(subprocess.CalledProcessError):
                self.apply(installer, True)
            self.assertFalse(any(c[:2] == ('systemctl', 'stop') for c in calls))
            self.assertIn('Petrel.service', active)
            self.assertFalse(installer.path(MANIFEST).exists())
            self.assertFalse(installer.path(broker_binary(ROOT)).exists())

    def test_cached_install_repairs_directory_permissions_under_private_umask(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            self.apply(installer, True)
            directory = installer.path(BROKER_DIRECTORY)
            directory.chmod(0o700)
            directory.parent.chmod(0o700)
            saved = os.umask(0o077)
            try:
                self.apply(installer, True)
            finally:
                os.umask(saved)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
            self.assertEqual(directory.parent.stat().st_mode & 0o111, 0o111)
            self.assertEqual(builder.call_count, 1)

    def test_existing_python_manifest_migrates_and_failure_restores_old_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            self.apply(installer, True)
            old = json.loads(installer.path(MANIFEST).read_text())
            del old['broker']
            installer.path(MANIFEST).write_text(json.dumps(old))
            unit = installer.path('/etc/systemd/system/' + SERVICE)
            unit.write_text('original Python service')
            installer.path(broker_binary(ROOT)).unlink()
            fail.append(('systemctl', 'enable', '--now', SERVICE))
            with self.assertRaises(subprocess.CalledProcessError):
                self.apply(installer, True)
            self.assertEqual(json.loads(installer.path(MANIFEST).read_text()), old)
            self.assertEqual(unit.read_text(), 'original Python service')
            self.assertIn(SERVICE, active)
            self.assertFalse(installer.path(broker_binary(ROOT)).exists())
            self.apply(installer, True)
            self.assertEqual(json.loads(installer.path(MANIFEST).read_text())['broker'], broker_binary(ROOT))
            self.assertIn(quote(broker_binary(ROOT)), unit.read_text())

    def test_source_update_keeps_rollback_binary_until_transition_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installer, active, calls, fail, builder = self.fixture(root)
            self.apply(installer, True)
            old_binary = installer.path(broker_binary(ROOT))
            changed = root / 'checkout'
            shutil.copytree(ROOT / 'native', changed / 'native')
            shutil.copytree(ROOT / 'kernel/dwin_uart', changed / 'kernel/dwin_uart')
            with (changed / 'native/dwin_broker.c').open('a') as f:
                f.write('\n/* new source version */\n')
            new_binary = installer.path(broker_binary(changed))
            fail.append(('systemctl', 'enable', '--now', SERVICE))
            with self.assertRaises(subprocess.CalledProcessError):
                installer.apply(True, changed, Path('/home/printer'), 'printer', '/dev/ttyAMA0')
            self.assertTrue(old_binary.exists())
            self.assertFalse(new_binary.exists())
            self.assertEqual(json.loads(installer.path(MANIFEST).read_text())['broker'], broker_binary(ROOT))
            installer.apply(True, changed, Path('/home/printer'), 'printer', '/dev/ttyAMA0')
            self.assertFalse(old_binary.exists())
            self.assertTrue(new_binary.exists())

    def test_startup_refresh_updates_native_without_restarting_own_ui_or_moonraker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installer, active, calls, fail, builder = self.fixture(root)
            self.apply(installer, True)
            changed = root / 'checkout'
            shutil.copytree(ROOT / 'native', changed / 'native')
            shutil.copytree(ROOT / 'kernel/dwin_uart', changed / 'kernel/dwin_uart')
            with (changed / 'native/dwin_broker.c').open('a') as stream:
                stream.write('\n/* updated broker */\n')
            calls.clear()
            installer.apply(True, changed, Path('/home/printer'), 'printer',
                            '/dev/ttyAMA0', manage_ui=False, restart_moonraker=False)
            self.assertTrue(installer.path(broker_binary(changed)).exists())
            self.assertFalse(any(c[:2] in (('systemctl', 'start'), ('systemctl', 'stop'),
                                          ('systemctl', 'restart')) and
                                 c[-1] in ('Petrel.service', 'moonraker.service') for c in calls))
            calls.clear()
            installer.busy.return_value = [123]
            installer.apply(True, changed, Path('/home/printer'), 'printer',
                            '/dev/ttyAMA0', manage_ui=False, restart_moonraker=False)
            self.assertFalse(any(c[:2] == ('systemctl', 'stop') for c in calls))
            dropin = installer.path(DROPIN).read_text()
            self.assertIn('ExecStartPre=+/usr/bin/python3 ', dropin)
            self.assertIn('--refresh-installed', dropin)
            self.assertIn('TimeoutStartSec=900', dropin)

    def test_startup_refresh_build_failure_retains_running_broker(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            self.apply(installer, True)
            before = installer.path(MANIFEST).read_text()
            installer.path(broker_binary(ROOT)).unlink()
            installer.broker_builder.side_effect = RuntimeError('compile failure')
            calls.clear()
            with self.assertRaisesRegex(RuntimeError, 'compile failure'):
                installer.apply(True, ROOT, Path('/home/printer'), 'printer',
                                '/dev/ttyAMA0', manage_ui=False, restart_moonraker=False)
            self.assertEqual(installer.path(MANIFEST).read_text(), before)
            self.assertIn(SERVICE, active)
            self.assertFalse(any(c[:2] == ('systemctl', 'stop') for c in calls))

    def test_refresh_cli_uses_manifest_and_skips_nested_installer_lock(self):
        from types import SimpleNamespace
        from tools import dwin_uart_install as module
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo = home / 'Petrel'
            repo.mkdir()
            manifest = home / 'manifest.json'
            manifest.write_text(json.dumps({'version': source_version(ROOT),
                'user': 'printer', 'repo': str(repo), 'port': '/dev/ttyAMA0'}))
            argv = ['installer', '--refresh-installed', '--repo', str(repo),
                    '--home', str(home), '--user', 'printer']
            with patch.object(sys, 'argv', argv), patch.object(module, 'MANIFEST', str(manifest)), \
                 patch.object(module, 'LOCK', str(home / 'lock')), \
                 patch.object(module.os, 'geteuid', return_value=0), \
                 patch.object(module.pwd, 'getpwnam', return_value=SimpleNamespace(pw_dir=str(home))), \
                 patch.object(module, 'Installer') as factory, patch.object(module.fcntl, 'flock') as flock:
                module.main()
                factory.return_value.apply.assert_called_once_with(
                    True, repo, home, 'printer', '/dev/ttyAMA0', None, None,
                    manage_ui=False, restart_moonraker=False)
                factory.reset_mock()
                flock.side_effect = BlockingIOError()
                module.main()
                factory.assert_not_called()
                flock.side_effect = None
                manifest.unlink()
                module.main()
                factory.assert_not_called()

    def test_manifest_rejects_foreign_binary_paths(self):
        for path in ('/bin/sh', BROKER_DIRECTORY + '/../../bin/sh', BROKER_DIRECTORY + '/broker-xyz'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                valid_manifest({'version': source_version(ROOT), 'broker': path})

    def test_real_native_build_is_versioned_executable_and_leaves_checkout_clean(self):
        if not shutil.which('make') or not shutil.which('cc'):
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                self.fail('Native build CI needs make and cc')
            self.skipTest('native toolchain unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o755)
            saved = os.umask(0o077)
            try:
                build_broker(ROOT, root)
            finally:
                os.umask(saved)
            binary = root / broker_binary(ROOT).lstrip('/')
            self.assertEqual(binary.stat().st_mode & 0o777, 0o755)
            for relative in ('usr', 'usr/local', 'usr/local/libexec', BROKER_DIRECTORY.lstrip('/')):
                self.assertEqual((root / relative).stat().st_mode & 0o111, 0o111)
            result = subprocess.run([str(binary), '--help'], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--backend', result.stdout)
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                result = subprocess.run(['sudo', '-n', '-u', 'nobody', '--', str(binary), '--help'],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            stat = binary.stat()
            build_broker(ROOT, root, execute=Mock(side_effect=AssertionError('unnecessary rebuild')))
            self.assertEqual(binary.stat().st_ino, stat.st_ino)
            self.assertEqual(list(binary.parent.glob('.build-*')), [])

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

    def test_updater_registration_tracks_optional_service_and_preserves_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer, active, calls, fail, builder = self.fixture(Path(tmp))
            conf = installer.path('/home/printer/printer_data/config/Petrel.conf')
            conf.parent.mkdir(parents=True)
            conf.write_text('[update_manager Petrel]\nmanaged_services: Petrel\n  Petrel-dwin\nrequirements: requirements.txt\n')
            registry = installer.path('/home/printer/printer_data/moonraker.asvc')
            registry.write_text('Petrel\nOtherService\n')
            self.apply(installer, True)
            self.assertIn('managed_services: Petrel\n', conf.read_text())
            self.assertNotIn('Petrel-dwin', conf.read_text())
            self.assertIn('requirements: requirements.txt\n', conf.read_text())
            self.assertEqual(registry.read_text(), 'Petrel\nOtherService\nPetrel-dwin\n')
            self.apply(installer, False)
            self.assertNotIn('Petrel-dwin', conf.read_text())
            self.assertEqual(registry.read_text(), 'Petrel\nOtherService\n')
            self.assertTrue(conf.exists())

    def test_configurator_persists_enable_and_disable_after_installer_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            bin_dir = home / 'bin'
            bin_dir.mkdir()
            command = bin_dir / 'sudo'
            command.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$TEST_HOME/sudo.log"\n')
            command.chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'], TEST_HOME=tmp)
            selection = home / 'selection.config'
            for enabled in ('y', 'n'):
                selection.write_text('CONFIG_PETREL_AXIS_TRAVEL=n\nCONFIG_PETREL_AUX_UART=' + enabled + '\n')
                result = subprocess.run([sys.executable, str(ROOT / 'tools/configure.py'),
                    '--home', tmp, '--user', 'user', '--apply-config', str(selection), '--no-restart'],
                    text=True, env=env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                flag = '1' if enabled == 'y' else '0'
                self.assertIn('PETREL_AUX_UART=' + flag + '\n',
                              (home / '.config/Petrel/Petrel.env').read_text())
            calls = (home / 'sudo.log').read_text()
            self.assertIn('--enabled 1', calls)
            self.assertIn('--enabled 0', calls)

    def test_generated_service_passes_real_systemd_unit_validation(self):
        verifier = shutil.which('systemd-analyze')
        if not verifier:
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                self.fail('CI must provide systemd-analyze for generated service verification')
            self.skipTest('systemd-analyze is unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'printer home'
            binary = home / 'petrel-env/bin/python'
            binary.parent.mkdir(parents=True)
            binary.symlink_to(sys.executable)
            repo = home / 'Petrel'
            repo.mkdir()
            unit = Path(tmp) / 'Petrel-dwin.service'
            text = service_text(repo, home, getpass.getuser(), '/dev/ttyAMA0', binary=binary)
            env = dict(os.environ, LC_ALL='C', SYSTEMD_LOG_COLOR='0')
            unit.write_text(text)
            result = subprocess.run([verifier, 'verify', '--man=no', str(unit)],
                                    text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # The original failure must be caught by the same real parser.
            unit.write_text(text.replace('[Service]\n',
                '[Service]\nWorkingDirectory=' + quote(str(repo)) + '\n'))
            result = subprocess.run([verifier, 'verify', '--man=no', str(unit)],
                                    text=True, capture_output=True, env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('WorkingDirectory=', result.stderr)

    def test_systemd_arguments_escape_specifiers_and_reject_newlines(self):
        self.assertEqual(quote('/tmp/with space%/a"b'), '"/tmp/with space%%/a\\"b"')
        with self.assertRaises(ValueError):
            quote('/dev/ttyAMA0\nExecStart=bad')


if __name__ == '__main__':
    unittest.main()
