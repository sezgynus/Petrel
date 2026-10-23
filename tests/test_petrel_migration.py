import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import petrel_migration as migration


ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def installed(self, home):
        legacy = migration.LEGACY_APP
        repo = home / legacy
        (repo / '.git').mkdir(parents=True)
        (repo / 'requirements.txt').write_text('Pillow==12.3.0\n')
        (repo / 'Petrel.service').write_bytes((ROOT / 'Petrel.service').read_bytes())
        config = home / '.config' / legacy
        config.mkdir(parents=True)
        self.original_env = ('MOONRAKER_API_KEY=secret-DWIN_TOKEN\n'
                             'DWIN_SERIAL_PORT=/dev/ttyS0\nDWIN_EMULATOR=1\n'
                             'DWIN_SETTINGS_FILE=' + str(config / 'presets.json') + '\n')
        (config / (legacy + '.env')).write_text(self.original_env)
        (config / 'presets.json').write_bytes(b'{"personal": "unchanged"}')
        conf = home / 'printer_data/config'
        conf.mkdir(parents=True)
        (conf / 'moonraker.conf').write_text('[server]\nport: 7125\n[include ' + legacy + '.conf]\n')
        (conf / (legacy + '.conf')).write_text(
            '[update_manager ' + legacy + ']\ntype: git_repo\nchannel: dev\n'
            'path: ~/' + legacy + '\nvirtualenv: ~/klipperdwin-env\n'
            'origin: https://github.com/sezgynus/' + legacy + '.git\n'
            'requirements: requirements.txt\nmanaged_services: ' + legacy + '\n')
        (home / 'printer_data/moonraker.asvc').write_text('klipper\nmoonraker\n' + legacy + '\n')
        system = home / 'systemd'
        system.mkdir()
        (system / (legacy + '.service')).write_text('SupplementaryGroups=dialout gpio\n')
        (home / migration.LEGACY_ENV).mkdir()
        (home / (legacy + '-screenshots')).mkdir()
        m = migration.Migration(home, 'user', system_dir=system)
        m.wait_for_updater = Mock()
        m.command = Mock(return_value='')
        def user_command(*args):
            if args[0] == 'git' and 'get-url' in args:
                return 'https://github.com/sezgynus/' + legacy + '.git'
            if args[0] == '/usr/bin/python3':
                m.venv.mkdir(exist_ok=True)
            return ''
        m.as_user = Mock(side_effect=user_command)
        return m

    @patch('petrel_migration.time.sleep')
    @patch('petrel_migration.shutil.chown')
    def test_installed_update_moves_every_identity_and_preserves_settings(self, *_):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            m = self.installed(home)
            m.run()
            self.assertFalse(m.old_repo.exists())
            self.assertFalse(m.old_config.exists())
            self.assertTrue((m.repo / '.git').exists())
            env = (m.config / 'Petrel.env').read_text()
            self.assertIn('PETREL_SERIAL_PORT=/dev/ttyS0', env)
            self.assertIn('PETREL_EMULATOR=1', env)
            self.assertIn('secret-DWIN_TOKEN', env)
            self.assertIn(str(m.config / 'presets.json'), env)
            self.assertEqual((m.config / 'presets.json').read_bytes(), b'{"personal": "unchanged"}')
            self.assertIn('[update_manager Petrel]', m.update.read_text())
            self.assertIn('managed_services: Petrel', m.update.read_text())
            self.assertIn('origin: ' + migration.ORIGIN, m.update.read_text())
            self.assertIn('[include Petrel.conf]', m.moonraker_config.read_text())
            self.assertEqual(m.asvc.read_text(), 'klipper\nmoonraker\nPetrel\n')
            unit = (m.system_dir / 'Petrel.service').read_text()
            self.assertIn('SupplementaryGroups=dialout gpio', unit)
            self.assertIn((m.venv / 'bin/python').as_posix(), unit.replace('\\', '/'))
            self.assertNotIn('@', unit)
            self.assertFalse((m.system_dir / (migration.LEGACY_APP + '.service')).exists())
            self.assertTrue((m.state / 'migration-complete').exists())
            self.assertTrue((m.state / 'previous-python').exists())
            self.assertTrue((home / 'Petrel-screenshots').exists())

    @patch('petrel_migration.subprocess.run')
    @patch('petrel_migration.time.sleep')
    @patch('petrel_migration.shutil.chown')
    def test_failed_service_start_restores_original_files_paths_and_origin(self, *_):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            m = self.installed(home)
            def command(*args):
                if 'is-active' in args:
                    raise RuntimeError('new service failed')
                return ''
            m.command.side_effect = command
            with self.assertRaisesRegex(RuntimeError, 'new service failed'):
                m.run()
            self.assertTrue(m.old_repo.exists())
            self.assertFalse(m.repo.exists())
            self.assertEqual((m.old_config / (migration.LEGACY_APP + '.env')).read_text(), self.original_env)
            self.assertFalse(m.config.exists())
            self.assertTrue(m.old_update.exists())
            self.assertFalse(m.update.exists())
            self.assertFalse((m.system_dir / 'Petrel.service').exists())
            self.assertIn(migration.LEGACY_APP, m.asvc.read_text())
            self.assertTrue((m.state / 'migration-failed').exists())
            m.as_user.assert_any_call('git', '-C', m.old_repo, 'remote', 'set-url', 'origin', m.original_origin)

    def test_destination_collision_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.installed(Path(tmp))
            m.repo.mkdir()
            (m.repo / 'personal-file').write_text('keep')
            with self.assertRaisesRegex(RuntimeError, 'overwrite'):
                m.run()
            m.command.assert_not_called()
            self.assertEqual((m.repo / 'personal-file').read_text(), 'keep')
            self.assertTrue(m.old_repo.exists())

    @patch('petrel_migration.time.sleep')
    @patch('petrel_migration.shutil.chown')
    def test_runtime_created_cache_and_capture_directories_do_not_block_migration(self, *_):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            m = self.installed(home)
            old_cache = home / '.cache' / (migration.LEGACY_APP + '-emulator')
            old_cache.mkdir(parents=True)
            (old_cache / 'old-data').write_text('old cache')
            new_cache = home / '.cache/Petrel-emulator'
            new_cache.mkdir()
            (new_cache / 'new-data').write_text('active cache')
            (home / 'Petrel-screenshots').mkdir()
            (home / 'Petrel-screenshots/new.png').write_bytes(b'new capture')
            (home / (migration.LEGACY_APP + '-screenshots') / 'old.png').write_bytes(b'old capture')
            m.run()
            self.assertEqual((new_cache / 'new-data').read_text(), 'active cache')
            self.assertEqual((m.state / 'previous-emulator-cache/old-data').read_text(), 'old cache')
            self.assertEqual((home / 'Petrel-screenshots/new.png').read_bytes(), b'new capture')
            self.assertEqual((m.state / 'previous-screenshots/old.png').read_bytes(), b'old capture')

    @patch('petrel_migration.subprocess.run')
    @patch('petrel_migration.time.sleep')
    @patch('petrel_migration.shutil.chown')
    def test_archive_moves_are_rolled_back_without_touching_existing_cache(self, *_):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            m = self.installed(home)
            old_cache = home / '.cache' / (migration.LEGACY_APP + '-emulator')
            old_cache.mkdir(parents=True)
            (old_cache / 'old-data').write_text('old')
            new_cache = home / '.cache/Petrel-emulator'
            new_cache.mkdir()
            (new_cache / 'new-data').write_text('new')
            def command(*args):
                if 'is-active' in args:
                    raise RuntimeError('new service failed')
                return ''
            m.command.side_effect = command
            with self.assertRaises(RuntimeError):
                m.run()
            self.assertEqual((old_cache / 'old-data').read_text(), 'old')
            self.assertEqual((new_cache / 'new-data').read_text(), 'new')

    def test_configuration_converter_only_changes_this_application(self):
        text = '[update_manager other]\npath: ~/other\norigin: custom\n'
        text += '[update_manager ' + migration.LEGACY_APP + ']\npath: ~/old\n'
        text += '[server]\nport: 7125\n'
        converted = migration.convert_moonraker(text)
        self.assertIn('[update_manager other]\npath: ~/other\norigin: custom', converted)
        self.assertIn('[update_manager Petrel]\npath: ~/Petrel', converted)
        self.assertTrue(converted.endswith('[server]\nport: 7125\n'))

    @patch('petrel_migration.time.sleep')
    @patch('petrel_migration.urlopen')
    def test_migration_waits_for_moonraker_to_finish_full_update(self, request, sleep):
        from io import BytesIO
        with tempfile.TemporaryDirectory() as tmp:
            m = self.installed(Path(tmp))
            request.side_effect = [BytesIO(b'{"result":{"busy":true}}'),
                                   BytesIO(b'{"result":{"busy":false}}')]
            migration.Migration.wait_for_updater(m)
            sleep.assert_called_once_with(2)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args.args[0].get_header('X-api-key'), 'secret-DWIN_TOKEN')
            m.command.assert_not_called()

    @patch('petrel_migration.subprocess.run')
    def test_developer_checkout_does_not_launch_migration(self, command):
        migration.bootstrap()
        command.assert_not_called()

    @patch('petrel_migration.subprocess.run')
    def test_legacy_start_schedules_independent_job_and_maps_runtime_settings(self, command):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            command.return_value.returncode = 0
            env = {'DWIN_SERIAL_PORT': '/dev/legacy', 'MOONRAKER_API_KEY': 'private'}
            with patch('petrel_migration.sys.platform', 'linux'), patch('petrel_migration.Path.home', return_value=home), \
                    patch('petrel_migration.Path.owner', return_value='user'), \
                    patch('petrel_migration.__file__', str(home / migration.LEGACY_APP / 'petrel_migration.py')), \
                    patch.dict(os.environ, env, clear=True):
                self.assertTrue(migration.bootstrap())
                self.assertEqual(os.environ['PETREL_SERIAL_PORT'], '/dev/legacy')
            args = command.call_args.args[0]
            self.assertIn('systemd-run', args)
            self.assertIn('--on-active=15s', args)
            self.assertNotIn('private', args)

    def test_legacy_eeprom_settings_remain_readable(self):
        import struct
        import zlib
        import display_settings
        from buzzer_control import Settings
        for magic in (b'KDWDSPL1', b'KDWDSPL2'):
            payload = struct.pack('>8sBBB1x', magic, 80, 5, 20)
            self.assertEqual(display_settings.decode(payload + struct.pack('>I', zlib.crc32(payload))),
                             (80, 5, 10 if magic.endswith(b'1') else 20))
        setting = Settings(enabled=True, volume=70, click=3, encoder=1)
        body = (struct.pack('>8sBBB', b'KDWBZR01', 70, 3, 1) +
                b'Buzzer\0').ljust(124, b'\0')
        self.assertEqual(Settings.decode(body + struct.pack('>I', zlib.crc32(body))), setting)

    @patch('petrel_migration.subprocess.run')
    @patch('petrel_migration.shutil.chown')
    def test_preparation_failure_resumes_old_service_without_rescheduling(self, _, command):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            m = self.installed(Path(tmp))
            m.run = Mock(side_effect=RuntimeError('dependency download failed'))
            account = SimpleNamespace(pw_uid=1000, pw_dir=tmp)
            pwd = SimpleNamespace(getpwnam=Mock(return_value=account))
            with patch.dict('sys.modules', {'pwd': pwd}), \
                    patch('petrel_migration.os.geteuid', return_value=0, create=True), \
                    patch('petrel_migration.Migration', return_value=m), \
                    patch('sys.argv', ['petrel_migration.py', '--user', 'user']), \
                    self.assertLogs(level='ERROR'):
                self.assertEqual(migration.main(), 1)
            self.assertTrue((m.state / 'migration-failed').exists())
            command.assert_called_once_with(
                ['systemctl', 'start', migration.LEGACY_APP + '.service'],
                check=False, capture_output=True)
