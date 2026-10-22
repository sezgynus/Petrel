import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from tools.configure import Configuration, apply, choose, collect, config_text, defaults, read_settings, render_env, validate

ROOT = Path(__file__).resolve().parents[1]


class KconfigConfigurationTests(unittest.TestCase):
    def values(self, home):
        values = defaults(home)
        values['PETREL_AXIS_TRAVEL'] = 'n'
        return values

    def test_real_schema_imports_legacy_bool_formats_and_hidden_preferences(self):
        home = Path('/home/printer')
        values = read_settings(home, 'PETREL_REMOTE=false\nPETREL_EMULATOR=on\n'
            'PETREL_AXIS_TRAVEL=0\nPETREL_KLIPPER_DIR="/opt/custom klipper"\n'
            'PETREL_REMOTE_PORT=8099\nPETREL_BUTTON_PIN=13\n')
        config = Configuration(ROOT, values)
        self.assertFalse(config.warnings)
        self.assertEqual(config.syms['PETREL_KLIPPER_DIR'].visibility, 0)
        self.assertEqual(collect(config)['PETREL_KLIPPER_DIR'], '/opt/custom klipper')
        self.assertEqual(collect(config)['PETREL_REMOTE_PORT'], '8099')
        config.syms['PETREL_AXIS_TRAVEL'].set_value('y')
        config.syms['PETREL_REMOTE'].set_value('y')
        self.assertEqual(config.syms['PETREL_KLIPPER_DIR'].str_value, '/opt/custom klipper')
        self.assertEqual(config.syms['PETREL_REMOTE_PORT'].str_value, '8099')
        self.assertEqual(config.syms['PETREL_BUTTON_PIN'].str_value, '13')

    def test_nfc_is_an_independent_opt_in_from_dwin_uart(self):
        values = self.values(Path('/home/printer'))
        self.assertEqual(values['PETREL_NFC'], 'n')
        config = Configuration(ROOT, values)
        config.syms['PETREL_NFC'].set_value('y')
        self.assertEqual(collect(config)['PETREL_NFC'], 'y')
        self.assertEqual(collect(config)['PETREL_AUX_UART'], 'n')

    def test_cancel_without_save_does_not_offer_apply(self):
        values = self.values(Path('/home/printer'))
        config = Configuration(ROOT, values)
        confirm = Mock(side_effect=AssertionError('Must not offer unsaved settings'))
        def launch(cfg):
            cfg.load_config(os.environ['KCONFIG_CONFIG'])
            cfg.syms['PETREL_AUX_UART'].set_value('y')
        self.assertIsNone(choose(config, values, launch, confirm))
        confirm.assert_not_called()

    def test_declining_apply_preserves_runtime_and_staged_ui_choices(self):
        values = self.values(Path('/home/printer'))
        config = Configuration(ROOT, values)
        def launch(cfg):
            cfg.load_config(os.environ['KCONFIG_CONFIG'])
            cfg.syms['PETREL_AUX_UART'].set_value('y')
            cfg.write_config()
        self.assertIsNone(choose(config, values, launch, lambda _: 'n'))

    def test_only_last_saved_snapshot_is_applied_not_later_unsaved_edits(self):
        values = self.values(Path('/home/printer'))
        config = Configuration(ROOT, values)
        def launch(cfg):
            cfg.load_config(os.environ['KCONFIG_CONFIG'])
            cfg.syms['PETREL_EMULATOR'].set_value('y')
            cfg.write_config()
            cfg.syms['PETREL_EMULATOR'].set_value('n')
        selected = choose(config, values, launch, lambda _: 'yes')
        self.assertEqual(selected['PETREL_EMULATOR'], 'y')
        self.assertEqual(collect(config)['PETREL_EMULATOR'], 'n')

    def test_config_format_roundtrip_keeps_hidden_values_and_literal_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.values(Path(tmp))
            values['PETREL_KLIPPER_DIR'] = '/opt/klipper "custom" \\ $(literal)'
            path = Path(tmp) / 'selection.config'
            path.write_text(config_text(values))
            config = Configuration(ROOT, defaults(Path(tmp)))
            config.load_config(str(path))
            self.assertFalse(config.warnings)
            self.assertEqual(collect(config), values)

    def test_private_multiline_records_survive_and_do_not_become_settings(self):
        home = Path('/home/printer')
        original = 'MOONRAKER_API_KEY="private\nPETREL_BUTTON_PIN=22\nend"\nCUSTOM=$(literal)\n'
        values = read_settings(home, original)
        self.assertEqual(values['PETREL_BUTTON_PIN'], '20')
        self.assertIn(original, render_env(values, original))
        self.assertNotIn('private', config_text(values))

    def test_invalid_fields_fail_before_any_installation_or_file_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for name, value in [('ENCODER_A_GPIO', '19'), ('PETREL_REMOTE_PORT', '70000'),
                                ('MOONRAKER_URL', 'file:///tmp'), ('PETREL_REQUEST_TIMEOUT', 'nan'),
                                ('PETREL_SERIAL_PORT', '/dev/ttyDWIN0'), ('PETREL_SETTINGS_FILE', 'relative'),
                                ('PETREL_POWER_DEVICE', 'Printer\nBAD=value')]:
                selected = self.values(home)
                selected[name] = value
                axis, dwin, writer = Mock(), Mock(), Mock()
                with self.assertRaises(ValueError):
                    apply(selected, repo=ROOT, home=home, user='user', original='',
                          axis=axis, dwin=dwin, writer=writer, dwin_manifest=home / 'none')
                axis.assert_not_called()
                dwin.assert_not_called()
                writer.assert_not_called()

    def test_failed_uart_install_rolls_back_completed_counter_install_and_keeps_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/Petrel/Petrel.env'
            path.parent.mkdir(parents=True)
            path.write_text('PETREL_AXIS_TRAVEL=0\nPRIVATE=value\n')
            original = path.read_text()
            values = read_settings(home, original)
            values.update(PETREL_AXIS_TRAVEL='y', PETREL_AUX_UART='y')
            axis = Mock(return_value=True)
            dwin = Mock(side_effect=RuntimeError('busy UART'))
            with self.assertRaisesRegex(RuntimeError, 'busy UART'):
                apply(values, repo=ROOT, home=home, user='user', original=original,
                      axis=axis, dwin=dwin, dwin_manifest=home / 'none')
            self.assertEqual([call.args[0] for call in axis.call_args_list], [True, False])
            self.assertEqual(path.read_text(), original)

    def test_environment_write_failure_undoes_successful_uart_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            selected = self.values(home)
            selected['PETREL_AUX_UART'] = 'y'
            axis, dwin = Mock(return_value=False), Mock()
            writer = Mock(side_effect=OSError('disk failure'))
            with self.assertRaisesRegex(OSError, 'disk failure'):
                apply(selected, repo=ROOT, home=home, user='user', original='',
                      axis=axis, dwin=dwin, writer=writer, dwin_manifest=home / 'none')
            self.assertEqual([call.args[3] for call in dwin.call_args_list], [True, False])
            self.assertFalse((home / '.config/Petrel/Petrel.env').exists())

    def test_nfc_dependency_is_applied_and_removed_without_enabling_dwin(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            values = self.values(home)
            values['PETREL_NFC'] = 'y'
            axis, dwin, nfc = Mock(return_value=False), Mock(), Mock()
            apply(values, repo=ROOT, home=home, user='user', original='', axis=axis,
                  dwin=dwin, nfc=nfc, dwin_manifest=home / 'none', nfc_manifest=home / 'no-nfc')
            nfc.assert_called_once_with(ROOT, True)
            dwin.assert_not_called()
            self.assertIn('PETREL_NFC=1\n', (home / '.config/Petrel/Petrel.env').read_text())

            original = (home / '.config/Petrel/Petrel.env').read_text()
            values = read_settings(home, original)
            values['PETREL_NFC'] = 'n'
            nfc.reset_mock()
            apply(values, repo=ROOT, home=home, user='user', original=original, axis=axis,
                  dwin=dwin, nfc=nfc, dwin_manifest=home / 'none', nfc_manifest=home / 'no-nfc')
            nfc.assert_called_once_with(ROOT, False)
            dwin.assert_not_called()

    def test_settings_changed_during_menu_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/Petrel/Petrel.env'
            path.parent.mkdir(parents=True)
            path.write_text('FUTURE=changed\n')
            axis = Mock()
            with self.assertRaisesRegex(ValueError, 'changed while'):
                apply(self.values(home), repo=ROOT, home=home, user='user', original='',
                      axis=axis, dwin_manifest=home / 'none')
            axis.assert_not_called()
            self.assertEqual(path.read_text(), 'FUTURE=changed\n')

    def test_unattended_invocation_requires_an_explicit_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / 'tools/configure.py'),
                '--home', tmp, '--user', 'user'], text=True, input='', capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--apply-config', result.stderr)
            self.assertFalse((Path(tmp) / '.config/Petrel/Petrel.env').exists())

    @unittest.skipUnless(os.name == 'posix', 'Menu smoke test needs a POSIX PTY')
    def test_real_curses_menu_opens_and_cancel_does_not_install(self):
        import fcntl
        import select
        import struct
        import termios
        import time
        with tempfile.TemporaryDirectory() as tmp:
            master, slave = os.openpty()
            try:
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 120, 0, 0))
                env = dict(os.environ, TERM='xterm', LC_ALL='C.UTF-8')
                process = subprocess.Popen([sys.executable, str(ROOT / 'tools/configure.py'),
                    '--home', tmp, '--user', 'user'], stdin=slave, stdout=slave, stderr=slave, env=env)
                try:
                    output = bytearray()
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline and b'Petrel configuration' not in output:
                        if select.select([master], [], [], .1)[0]:
                            output.extend(os.read(master, 65536))
                        if process.poll() is not None:
                            break
                    self.assertIn(b'Petrel configuration', output, output.decode(errors='replace'))
                    os.write(master, b'q')
                    # Quit may ask to save because hidden imported values differ
                    # from their inactive defaults. Decline that save explicitly.
                    os.write(master, b'n')
                    while process.poll() is None and time.monotonic() < deadline:
                        if select.select([master], [], [], .1)[0]:
                            output.extend(os.read(master, 65536))
                    self.assertEqual(process.poll(), 2, output.decode(errors='replace'))
                    self.assertFalse((Path(tmp) / '.config/Petrel/Petrel.env').exists())
                    self.assertFalse((Path(tmp) / '.config/Petrel/axis-travel-install.json').exists())
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
            finally:
                os.close(master)
                os.close(slave)

    def test_unknown_headless_symbols_fail_without_installing(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'bad.config'
            file.write_text('CONFIG_PETREL_AXIS_TRAVEL=n\nCONFIG_UNKNOWN_PETREL_SETTING=y\n')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/configure.py'),
                '--home', tmp, '--user', 'user', '--apply-config', str(file)],
                text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unknown settings', result.stderr)
            self.assertFalse((Path(tmp) / '.config/Petrel/Petrel.env').exists())

    def test_shell_entry_point_reuses_existing_python_and_exports_without_applying(self):
        import pwd
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            python = home / 'petrel-env/bin/python'
            python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
            binaries = home / 'bin'
            binaries.mkdir()
            getent = binaries / 'getent'
            getent.write_text('#!/bin/sh\necho "user:x:1000:1000::${TEST_HOME}:/bin/bash"\n')
            getent.chmod(0o755)
            username = pwd.getpwuid(os.getuid()).pw_name
            env = dict(os.environ, USER=username, SUDO_USER=username, TEST_HOME=tmp,
                       PATH=str(binaries) + ':' + os.environ['PATH'])
            destination = home / 'export.config'
            result = subprocess.run(['bash', str(ROOT / 'configure.sh'), '--export-config', str(destination)],
                                    text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(destination.exists())
            self.assertFalse((home / '.config/Petrel/Petrel.env').exists())

    def test_export_only_does_not_apply_or_expose_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/Petrel/Petrel.env'
            path.parent.mkdir(parents=True)
            original = 'MOONRAKER_API_KEY=private\nPETREL_EMULATOR=1\n'
            path.write_text(original)
            destination = home / 'settings.config'
            result = subprocess.run([sys.executable, str(ROOT / 'tools/configure.py'),
                '--home', tmp, '--user', 'user', '--export-config', str(destination)],
                text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('private', destination.read_text())
            self.assertIn('CONFIG_PETREL_EMULATOR=y', destination.read_text())
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(), original)


if __name__ == '__main__':
    unittest.main()
