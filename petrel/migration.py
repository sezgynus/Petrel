"""One-time installed-system migration; legacy names are confined to this module.

The old updater can only restart its already-installed service. That first start
schedules a separate systemd job, so stopping that service cannot kill migration.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen

LEGACY_APP = 'KlipperDWIN'
LEGACY_ENV = 'klipperdwin-env'
ORIGIN = 'https://github.com/sezgynus/Petrel.git'


def convert_environment(text, home):
    """Rename setting keys and managed paths without altering secrets/custom paths."""
    lines = []
    for line in text.splitlines(keepends=True):
        key, sep, value = line.partition('=')
        if sep and key.strip().startswith('DWIN_'):
            key = key.replace('DWIN_', 'PETREL_', 1)
            if key.strip() in ('PETREL_SETTINGS_FILE', 'PETREL_EMULATOR_SOCKET',
                               'PETREL_SCREENSHOT_DIRECTORY', 'PETREL_EMULATOR_FONT'):
                value = value.replace(str(home / '.config' / LEGACY_APP), str(home / '.config/Petrel'))
                value = value.replace(str(home / (LEGACY_APP + '-screenshots')), str(home / 'Petrel-screenshots'))
                value = value.replace(str(home / '.cache' / (LEGACY_APP + '-emulator')), str(home / '.cache/Petrel-emulator'))
                value = value.replace(str(home / LEGACY_APP), str(home / 'Petrel'))
                value = value.replace('~/.config/' + LEGACY_APP, '~/.config/Petrel')
            line = key + sep + value
        lines.append(line)
    return ''.join(lines)


def convert_moonraker(text):
    """Edit only our include/updater; other apps and user configuration stay intact."""
    lines, ours = [], False
    replacements = {'path': '~/Petrel', 'virtualenv': '~/petrel-env',
                    'origin': ORIGIN, 'managed_services': 'Petrel'}
    for line in text.splitlines(keepends=True):
        section = re.match(r'\s*\[([^]]+)\]\s*(?:[#;].*)?$', line.strip())
        if section:
            name = section[1].strip()
            ours = name.casefold() == ('update_manager ' + LEGACY_APP).casefold()
            if ours:
                line = '[update_manager Petrel]\n'
            elif name.casefold() == ('include ' + LEGACY_APP + '.conf').casefold():
                line = '[include Petrel.conf]\n'
        elif ours:
            match = re.match(r'(\s*)([\w]+)\s*[:=]', line)
            if match and match[2].lower() in replacements:
                line = match[1] + match[2] + ': ' + replacements[match[2].lower()] + '\n'
        lines.append(line)
    return ''.join(lines)


def bootstrap():
    """Called before GPIO/UART starts; harmless in new installs and developer trees."""
    home = Path.home()
    repo = Path(__file__).resolve().parents[1]
    if sys.platform != 'linux' or repo != home / LEGACY_APP:
        return
    for key, value in tuple(os.environ.items()):
        if key.startswith('DWIN_'):
            os.environ.setdefault('PETREL_' + key[5:], value)
    state = home / '.local/state/Petrel'
    if (state / 'migration-failed').exists():
        logging.error('Petrel migration needs attention: sudo python3 %s --user %s',
                      repo / 'petrel/migration.py', home.owner())
        return
    args = ['sudo', '-n', 'systemd-run', '--quiet', '--collect',
            '--unit=Petrel-migration', '--on-active=15s',
            '/usr/bin/python3', str(repo / 'petrel/migration.py'), '--user', home.owner()]
    if os.environ.get('MOONRAKER_CONFIG'):
        args += ['--moonraker-config', os.environ['MOONRAKER_CONFIG']]
    try:
        # No inherited secret environment or shell command interpolation.
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        if result.returncode:
            logging.error('Petrel automatic migration could not be scheduled. '
                          'Run sudo python3 %s --user %s to complete it.',
                          repo / 'petrel/migration.py', home.owner())
        else:
            logging.info('Petrel installation migration scheduled')
            return True
    except (OSError, subprocess.TimeoutExpired):
        logging.exception('Could not schedule Petrel installation migration')
    return False


class Migration:
    def __init__(self, home, user, system_dir=Path('/etc/systemd/system'), moonraker_config=None):
        self.home, self.user, self.system_dir = Path(home), user, Path(system_dir)
        self.old_repo, self.repo = self.home / LEGACY_APP, self.home / 'Petrel'
        self.old_config = self.home / '.config' / LEGACY_APP
        self.config = self.home / '.config/Petrel'
        self.venv = self.home / 'petrel-env'
        self.state = self.home / '.local/state/Petrel'
        self.moonraker_config = Path(moonraker_config).expanduser() if moonraker_config else None
        self.moves, self.files = [], {}

    def command(self, *args):
        return subprocess.run(list(args), check=True, text=True, capture_output=True, timeout=1800).stdout.strip()

    def as_user(self, *args):
        return self.command('runuser', '-u', self.user, '--', *map(str, args))

    def remember(self, path):
        path = Path(path)
        if path not in self.files:
            self.files[path] = (path.read_bytes(), path.stat()) if path.exists() else None

    def write(self, path, content):
        self.remember(path)
        path.write_text(content, encoding='utf-8')

    def move(self, source, target):
        if target.exists():
            raise RuntimeError('Destination already exists: ' + str(target))
        source.rename(target)
        self.moves.append((source, target))

    def preflight(self):
        if not (self.old_repo / '.git').exists():
            raise RuntimeError('Legacy installed Git checkout not found')
        if not (self.old_config / (LEGACY_APP + '.env')).is_file():
            raise RuntimeError('Legacy runtime settings not found')
        for target in (self.repo, self.config):
            if target.exists():
                raise RuntimeError('Refusing to overwrite existing ' + str(target))
        for source, target in self.optional_moves():
            if source.exists() and target.exists():
                raise RuntimeError('Refusing to merge existing ' + str(target))
        candidates = ([self.moonraker_config] if self.moonraker_config else
                      [self.home / 'printer_data/config/moonraker.conf', self.home / 'moonraker.conf']
                      + list(self.home.glob('*/config/moonraker.conf')))
        matches = {p for p in candidates if p.is_file() and
                   (LEGACY_APP in p.read_text(encoding='utf-8') or
                    (p.parent / (LEGACY_APP + '.conf')).exists())}
        if len(matches) != 1:
            raise RuntimeError('Specify the installed Moonraker config with --moonraker-config')
        self.moonraker_config = matches.pop()
        self.old_update = self.moonraker_config.parent / (LEGACY_APP + '.conf')
        self.update = self.moonraker_config.parent / 'Petrel.conf'
        if self.update.exists():
            raise RuntimeError('Existing Petrel updater must be resolved first')
        self.asvc = (self.moonraker_config.parent.parent if self.moonraker_config.parent.name == 'config'
                     else self.home / 'printer_data') / 'moonraker.asvc'
        self.original_origin = self.as_user('git', '-C', self.old_repo, 'remote', 'get-url', 'origin')

    def optional_moves(self):
        moves = []
        for source, target, backup_name in (
                (self.home / (LEGACY_APP + '-screenshots'), self.home / 'Petrel-screenshots', 'previous-screenshots'),
                (self.home / '.cache' / (LEGACY_APP + '-emulator'), self.home / '.cache/Petrel-emulator', 'previous-emulator-cache')):
            # The renamed runtime can create these destinations before migration
            # is authorized. Keep its files and archive the old directory intact.
            if target.exists():
                target = self.state / backup_name
                number = 1
                while target.exists():
                    target = self.state / (backup_name + '-' + str(number))
                    number += 1
            moves.append((source, target))
        return moves

    def wait_for_updater(self):
        """A full Moonraker update may continue after it restarts this service."""
        values = {}
        env = self.old_config / (LEGACY_APP + '.env')
        for line in env.read_text(encoding='utf-8').splitlines():
            key, separator, value = line.partition('=')
            if separator and key.strip() in ('MOONRAKER_URL', 'MOONRAKER_API_KEY'):
                parsed = shlex.split(value, comments=True)
                if len(parsed) == 1:
                    values[key.strip()] = parsed[0]
        url = values.get('MOONRAKER_URL', 'http://127.0.0.1:7125').rstrip('/') + '/machine/update/status'
        headers = {'X-Api-Key': values['MOONRAKER_API_KEY']} if values.get('MOONRAKER_API_KEY') else {}
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            try:
                with urlopen(Request(url, headers=headers), timeout=5) as response:
                    if json.load(response).get('result', {}).get('busy') is False:
                        return
            except (OSError, ValueError):
                pass  # A full update can briefly restart Moonraker itself.
            time.sleep(2)
        raise RuntimeError('Moonraker update did not finish; installation left unchanged')

    def run(self):
        logging.info('Checking installed Petrel migration prerequisites')
        self.preflight()
        self.wait_for_updater()
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.chown(self.state, user=self.user)
        # Build a new venv, never relocate scripts with old absolute shebangs.
        logging.info('Preparing Petrel Python environment; this may take a few minutes')
        self.as_user('/usr/bin/python3', '-m', 'venv', self.venv)
        self.as_user(self.venv / 'bin/python', '-m', 'pip', 'install', '-r', self.old_repo / 'requirements.txt')
        self.wait_for_updater()
        try:
            logging.info('Switching installation paths, service and Moonraker registration')
            self.command('systemctl', 'stop', LEGACY_APP + '.service')
            self.move(self.old_repo, self.repo)
            self.move(self.old_config, self.config)
            env = self.config / (LEGACY_APP + '.env')
            self.move(env, self.config / 'Petrel.env')
            env = self.config / 'Petrel.env'
            self.write(env, convert_environment(env.read_text(encoding='utf-8'), self.home))
            self.as_user('git', '-C', self.repo, 'remote', 'set-url', 'origin', ORIGIN)
            for source, target in self.optional_moves():
                if source.exists():
                    self.move(source, target)
            if self.old_update.exists():
                self.move(self.old_update, self.update)
                self.write(self.update, convert_moonraker(self.update.read_text(encoding='utf-8')))
            self.write(self.moonraker_config, convert_moonraker(self.moonraker_config.read_text(encoding='utf-8')))
            self.asvc.parent.mkdir(parents=True, exist_ok=True)
            content = self.asvc.read_text(encoding='utf-8') if self.asvc.exists() else ''
            lines = [line for line in content.splitlines() if line.strip() not in (LEGACY_APP, 'Petrel')]
            self.write(self.asvc, '\n'.join(lines + ['Petrel']) + '\n')
            template = (self.repo / 'Petrel.service').read_text(encoding='utf-8')
            template = template.replace('@PETREL_USER@', self.user).replace('@PETREL_HOME@', str(self.home))
            # Existing unit already contains the installer's valid supplementary groups.
            old_unit = (self.system_dir / (LEGACY_APP + '.service')).read_text(encoding='utf-8')
            groups = next((line for line in old_unit.splitlines() if line.startswith('SupplementaryGroups=')), '')
            self.write(self.system_dir / 'Petrel.service', template.replace('@SUPPLEMENTARY_GROUPS@', groups))
            self.command('systemctl', 'daemon-reload')
            self.command('systemctl', 'enable', '--now', 'Petrel.service')
            time.sleep(3)
            self.command('systemctl', 'is-active', '--quiet', 'Petrel.service')
            self.command('systemctl', 'restart', 'moonraker.service')
            self.command('systemctl', 'disable', LEGACY_APP + '.service')
            # Preserve a private recovery copy; never delete the old environment.
            old_venv = self.home / LEGACY_ENV
            if old_venv.exists():
                self.move(old_venv, self.state / 'previous-python')
            unit = self.system_dir / (LEGACY_APP + '.service')
            self.remember(unit)
            unit.unlink()
            self.command('systemctl', 'daemon-reload')
        except Exception:
            self.rollback()
            raise
        (self.state / 'migration-failed').unlink(missing_ok=True)
        (self.state / 'migration-complete').write_text('Petrel\n', encoding='utf-8')
        logging.info('Petrel migration complete')

    def rollback(self):
        subprocess.run(['systemctl', 'stop', 'Petrel.service'], check=False, capture_output=True)
        for path, original in self.files.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                content, stat = original
                path.write_bytes(content)
                os.chmod(path, stat.st_mode)
                if hasattr(os, 'chown'):
                    os.chown(path, stat.st_uid, stat.st_gid)
        for source, target in reversed(self.moves):
            if target.exists() and not source.exists():
                target.rename(source)
        self.as_user('git', '-C', self.old_repo, 'remote', 'set-url', 'origin', self.original_origin)
        (self.state / 'migration-failed').write_text('See journalctl -u Petrel-migration\n', encoding='utf-8')
        self.command('systemctl', 'daemon-reload')
        self.command('systemctl', 'enable', '--now', LEGACY_APP + '.service')
        self.command('systemctl', 'restart', 'moonraker.service')


def main():
    import pwd
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description='Migrate the installed display to Petrel')
    parser.add_argument('--user', required=True)
    parser.add_argument('--moonraker-config')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run this installed-system migration with sudo')
    account = pwd.getpwnam(args.user)
    if account.pw_uid == 0:
        parser.error('Select the non-root owner of the display installation')
    migration = Migration(account.pw_dir, args.user, moonraker_config=args.moonraker_config)
    try:
        migration.run()
    except Exception:
        logging.exception('Petrel migration failed; original installation retained/restored')
        # Preparation errors happen before the transaction: resume the old unit
        # as well, and suppress automatic rescheduling until a manual retry.
        if migration.old_repo.exists():
            migration.state.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.chown(migration.state, user=args.user)
            (migration.state / 'migration-failed').write_text(
                'See journalctl -u Petrel-migration.service\n', encoding='utf-8')
            subprocess.run(['systemctl', 'start', LEGACY_APP + '.service'],
                           check=False, capture_output=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
