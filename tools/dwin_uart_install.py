#!/usr/bin/env python3
"""Install/remove only Petrel-owned auxiliary UART resources.

Invoked by configure.sh/install.sh through sudo. Runtime broker is unprivileged.
Kernel build completes before switching the active display transport.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import stat
import subprocess
import tempfile

PACKAGE = 'petrel-dwin-uart'
SERVICE = 'Petrel-dwin.service'
MANIFEST = '/var/lib/Petrel/dwin-uart.json'
UNIT = '/etc/systemd/system/' + SERVICE
DROPIN = '/etc/systemd/system/Petrel.service.d/dwin-uart.conf'
RULES = '/etc/udev/rules.d/70-petrel-dwin-uart.rules'
MODULES = '/etc/modules-load.d/petrel-dwin-uart.conf'
BROKER_DIRECTORY = '/usr/local/libexec/petrel-dwin'
OWNED = (UNIT, DROPIN, RULES, MODULES, MANIFEST)


def run(*args, check=True):
    return subprocess.run(list(args), check=check, text=True, capture_output=True)


def atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    info = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix='.dwin-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.chmod(temporary, info.st_mode & 0o777 if info else 0o644)
        if info:
            os.chown(temporary, info.st_uid, info.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def quote(value):
    if any(ch in value for ch in ('\n', '\r', '\x00')):
        raise ValueError('Invalid systemd argument')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def source_version(repo):
    digest = hashlib.sha256()
    for name in ('dwin_uart.c', 'Makefile', 'dkms.conf'):
        digest.update((repo / 'kernel/dwin_uart' / name).read_bytes())
    return '0.1.0-' + digest.hexdigest()[:12]


def broker_binary(repo):
    digest = hashlib.sha256(platform.machine().encode())
    for name in ('dwin_broker.c', 'Makefile'):
        digest.update((repo / 'native' / name).read_bytes())
    return BROKER_DIRECTORY + '/broker-' + digest.hexdigest()[:12]


def build_broker(repo, root=Path('/'), execute=run):
    """Compile atomically to an immutable, root-owned versioned executable.

    The existing running binary remains available for rollback until the entire
    transport transition succeeds. Kernel build already supplies build-essential.
    """
    destination = root / broker_binary(repo).lstrip('/')
    if destination.is_file() and os.access(destination, os.X_OK) and destination.stat().st_size:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.build-', dir=destination.parent)
    os.close(fd)
    try:
        execute('make', '-B', '-C', str(repo / 'native'), 'OUTPUT=' + temporary)
        if not Path(temporary).stat().st_size:
            raise RuntimeError('Native DWIN broker build produced no executable')
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def valid_manifest(data):
    if data and not re.fullmatch(r'0\.1\.0-[0-9a-f]{12}', data.get('version', '')):
        raise ValueError('Invalid DWIN installation manifest; refusing removal')
    if data and data.get('broker') and not re.fullmatch(
            re.escape(BROKER_DIRECTORY) + r'/broker-[0-9a-f]{12}', data['broker']):
        raise ValueError('Invalid native DWIN broker path in installation manifest')
    return data


def port_users(path=Path('/dev/ttyDWIN0'), proc=Path('/proc')):
    """Detect users even when the port was opened through its enumeration alias."""
    try:
        device = path.stat().st_rdev
    except FileNotFoundError:
        return []
    users = []
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        try:
            for fd in (process / 'fd').iterdir():
                try:
                    info = fd.stat()
                    if stat.S_ISCHR(info.st_mode) and info.st_rdev == device:
                        users.append(int(process.name))
                        break
                except FileNotFoundError:
                    continue
        except (FileNotFoundError, PermissionError):
            continue
    return users


def header_packages(release):
    # First request the exact running kernel. Meta packages are fallbacks for
    # distro-managed Raspberry Pi kernels, never a reason to change the kernel.
    candidates = ['linux-headers-' + release]
    for flavor in ('rpi-2712', 'rpi-v8', 'rpi-v7l', 'rpi-v7'):
        if release.endswith(flavor):
            candidates.append('linux-headers-' + flavor)
    candidates.append('raspberrypi-kernel-headers')
    return candidates


def build(repo, version, root=Path('/'), execute=run):
    release = platform.release()
    execute('apt-get', 'update')
    execute('apt-get', 'install', '-y', 'dkms', 'build-essential', 'kmod', 'udev')
    headers = root / 'lib/modules' / release / 'build/Makefile'
    if not headers.exists():
        for package in header_packages(release):
            result = execute('apt-cache', 'show', package, check=False)
            if result.returncode == 0 and result.stdout.strip():
                execute('apt-get', 'install', '-y', package)
                if headers.exists():
                    break
        if not headers.exists():
            raise RuntimeError('Headers for running kernel ' + release + ' are unavailable; display transport was not changed')
    destination = root / 'usr/src' / (PACKAGE + '-' + version)
    if not destination.exists():
        destination.mkdir(parents=True)
        for name in ('dwin_uart.c', 'Makefile', 'dkms.conf'):
            shutil.copyfile(repo / 'kernel/dwin_uart' / name, destination / name)
        config = (destination / 'dkms.conf').read_text().replace('PACKAGE_VERSION="0.1.0"', 'PACKAGE_VERSION="' + version + '"')
        atomic(destination / 'dkms.conf', config)
    registered = execute('dkms', 'status', '-m', PACKAGE, '-v', version, check=False)
    if not registered.stdout.strip():
        execute('dkms', 'add', '-m', PACKAGE, '-v', version)
    execute('dkms', 'build', '-m', PACKAGE, '-v', version, '-k', release)
    execute('dkms', 'install', '-m', PACKAGE, '-v', version, '-k', release, '--force')


def service_text(repo, home, user, serial_port, *, binary=None):
    argv = ' '.join(quote(str(value)) for value in (
        binary if binary is not None else broker_binary(repo), '--port', serial_port))
    return f'''[Unit]
Description=DWIN shared UART transport
After=systemd-udev-trigger.service
StartLimitIntervalSec=0

[Service]
Type=simple
User={user}
Group=dialout
ExecStart={argv}
RuntimeDirectory=petrel-dwin
RuntimeDirectoryMode=0750
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
RestrictAddressFamilies=AF_UNIX
UMask=0007

[Install]
WantedBy=multi-user.target
'''


class Installer:
    def __init__(self, root=Path('/'), execute=run, busy=port_users, builder=build,
                 broker_builder=build_broker):
        self.root, self.execute, self.busy, self.builder = root, execute, busy, builder
        self.broker_builder = broker_builder

    def path(self, path):
        return self.root / path.lstrip('/')

    def active(self, service):
        return self.execute('systemctl', 'is-active', '--quiet', service, check=False).returncode == 0

    def registration_changes(self, enabled, updater, asvc):
        changes = {}
        if updater and self.path(str(updater)).exists():
            text = self.path(str(updater)).read_text()
            pattern = r'(?m)^managed_services:[^\n]*(?:\n[ \t]+[^\n]*)*'
            match = re.search(pattern, text)
            if match:
                services = [item for item in re.split(r'[,\s]+', match[0].split(':', 1)[1].strip())
                            if item and item != 'Petrel-dwin']
                if enabled:
                    services.append('Petrel-dwin')
                replacement = 'managed_services: ' + '\n  '.join(services)
                updated = text[:match.start()] + replacement + text[match.end():]
                if updated != text:
                    changes[str(updater)] = updated
        if asvc and self.path(str(asvc)).exists():
            text = self.path(str(asvc)).read_text()
            lines = [line for line in text.splitlines() if line.strip() != 'Petrel-dwin']
            if enabled:
                lines.append('Petrel-dwin')
            updated = '\n'.join(lines) + '\n'
            if updated != text:
                changes[str(asvc)] = updated
        return changes

    def apply(self, enabled, repo, home, user, serial_port, updater=None, asvc=None):
        manifest = self.path(MANIFEST)
        old = valid_manifest(json.loads(manifest.read_text()) if manifest.exists() else None)
        version = source_version(repo)
        binary = broker_binary(repo)
        new = {'version': version, 'user': user, 'port': serial_port, 'repo': str(repo),
               'broker': binary}
        if updater is None:
            updater = Path(old['updater']) if old and old.get('updater') else next(
                (p for p in (home / 'printer_data/config/Petrel.conf', home / 'Petrel.conf')
                 if self.path(str(p)).exists()), None)
        if asvc is None:
            asvc = Path(old['asvc']) if old and old.get('asvc') else home / 'printer_data/moonraker.asvc'
        if updater:
            new['updater'] = str(updater)
        if self.path(str(asvc)).exists():
            new['asvc'] = str(asvc)
        registration = self.registration_changes(enabled, updater, asvc)

        if (enabled and old == new and self.active(SERVICE)
                and all(self.path(p).exists() for p in OWNED)
                and self.path(binary).is_file() and self.path(binary).stat().st_size
                and os.access(self.path(binary), os.X_OK)):
            # Registry-only repairs need no UART restart, even with open clients.
            for p, text in registration.items():
                atomic(self.path(p), text)
            if registration and self.active('moonraker.service'):
                self.execute('systemctl', 'restart', 'moonraker.service')
            return
        if not enabled and old is None and not any(self.path(p).exists() for p in OWNED) and not registration:
            return
        users = self.busy()
        if users:
            raise RuntimeError('DWIN UART is in use by PID(s) ' + ', '.join(map(str, users)) + '; close the port before changing its installation')
        binary_existed = self.path(binary).exists()
        if enabled:
            try:
                self.builder(repo, version, self.root, self.execute)
                self.broker_builder(repo, self.root, self.execute)
            except BaseException:
                if not binary_existed:
                    self.path(binary).unlink(missing_ok=True)
                if not old or old['version'] != version:
                    self.execute('dkms', 'remove', '-m', PACKAGE, '-v', version, '--all', check=False)
                    shutil.rmtree(self.path('/usr/src/' + PACKAGE + '-' + version), ignore_errors=True)
                raise
        snapshot = {p: self.path(p).read_text() if self.path(p).exists() else None for p in (*OWNED, *registration)}
        was_active = self.active('Petrel.service')
        broker_active = self.active(SERVICE)
        broker_enabled = self.execute('systemctl', 'is-enabled', '--quiet', SERVICE, check=False).returncode == 0
        was_loaded = self.path('/sys/module/dwin_uart').exists()
        try:
            if was_active:
                self.execute('systemctl', 'stop', 'Petrel.service')
            self.execute('systemctl', 'stop', SERVICE, check=False)
            # rmmod refuses new opens racing the preflight check.
            if self.path('/sys/module/dwin_uart').exists():
                self.execute('modprobe', '-r', 'dwin_uart')
            if enabled:
                atomic(self.path(UNIT), service_text(repo, home, user, serial_port))
                atomic(self.path(DROPIN), '[Unit]\nWants=Petrel-dwin.service\nAfter=Petrel-dwin.service\n\n[Service]\nEnvironment=PETREL_DWIN_SOCKET=/run/petrel-dwin/display.sock\n')
                atomic(self.path(RULES), 'KERNEL=="ttyDWIN0", GROUP="dialout", MODE="0660", SYMLINK+="ttyS_DWIN0", ENV{ID_MM_DEVICE_IGNORE}="1"\nKERNEL=="dwin-uart-backend", GROUP="dialout", MODE="0660", ENV{ID_MM_DEVICE_IGNORE}="1"\n')
                atomic(self.path(MODULES), 'dwin_uart\n')
                self.execute('udevadm', 'control', '--reload-rules')
                self.execute('modprobe', 'dwin_uart')
                self.execute('udevadm', 'trigger', '--action=add', '--subsystem-match=tty')
                self.execute('udevadm', 'trigger', '--action=add', '--subsystem-match=misc')
                self.execute('udevadm', 'settle')
                self.execute('systemctl', 'daemon-reload')
                self.execute('systemctl', 'enable', '--now', SERVICE)
                if not self.path('/dev/ttyDWIN0').exists() or not self.active(SERVICE):
                    raise RuntimeError('DWIN driver or broker did not start')
                atomic(manifest, json.dumps(new, indent=2) + '\n')
            else:
                if old:
                    self.execute('dkms', 'remove', '-m', PACKAGE, '-v', old['version'], '--all')
                self.execute('systemctl', 'disable', SERVICE, check=False)
                for p in OWNED:
                    self.path(p).unlink(missing_ok=True)
                self.execute('udevadm', 'control', '--reload-rules')
                self.execute('systemctl', 'daemon-reload')
            for p, text in registration.items():
                atomic(self.path(p), text)
            if registration and self.active('moonraker.service'):
                self.execute('systemctl', 'restart', 'moonraker.service')
            if was_active:
                self.execute('systemctl', 'start', 'Petrel.service')
        except BaseException:
            self.execute('systemctl', 'stop', SERVICE, check=False)
            for p, text in snapshot.items():
                if text is None:
                    self.path(p).unlink(missing_ok=True)
                else:
                    atomic(self.path(p), text)
            if old:
                self.execute('dkms', 'install', '-m', PACKAGE, '-v', old['version'],
                             '-k', platform.release(), '--force', check=False)
            if not broker_enabled:
                self.execute('systemctl', 'disable', SERVICE, check=False)
            if not was_loaded:
                self.execute('modprobe', '-r', 'dwin_uart', check=False)
            if enabled and (not old or old['version'] != version):
                self.execute('dkms', 'remove', '-m', PACKAGE, '-v', version, '--all', check=False)
                shutil.rmtree(self.path('/usr/src/' + PACKAGE + '-' + version), ignore_errors=True)
            self.execute('systemctl', 'daemon-reload', check=False)
            self.execute('udevadm', 'control', '--reload-rules', check=False)
            if broker_active:
                self.execute('modprobe', 'dwin_uart', check=False)
                self.execute('systemctl', 'start', SERVICE, check=False)
            if registration and self.active('moonraker.service'):
                self.execute('systemctl', 'restart', 'moonraker.service', check=False)
            if was_active:
                self.execute('systemctl', 'start', 'Petrel.service', check=False)
            if enabled and not binary_existed:
                self.path(binary).unlink(missing_ok=True)
            raise
        # Only after the old unit no longer needs its immutable rollback binary.
        directory = self.path(BROKER_DIRECTORY)
        if directory.exists():
            for candidate in directory.iterdir():
                if (re.fullmatch(r'broker-[0-9a-f]{12}', candidate.name)
                        and (candidate.is_file() or candidate.is_symlink())):
                    if not enabled or candidate != self.path(binary):
                        candidate.unlink()
        # Remove superseded/disabled DKMS versions only after transport transition.
        if old and (not enabled or old['version'] != version):
            if enabled:
                result = self.execute('dkms', 'remove', '-m', PACKAGE, '-v', old['version'], '--all', check=False)
                if result.returncode:
                    print('Previous DWIN DKMS version could not be removed; its source was retained: ' + old['version'])
                    return
            shutil.rmtree(self.path('/usr/src/' + PACKAGE + '-' + old['version']), ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--enabled', choices=('0', '1'), required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--port', required=True)
    parser.add_argument('--updater', type=Path)
    parser.add_argument('--asvc', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run the installer through sudo')
    account = pwd.getpwnam(args.user)
    if args.home.resolve() != Path(account.pw_dir).resolve() or args.repo.resolve() != (args.home / 'Petrel').resolve():
        parser.error('Use the installed account and its ~/Petrel checkout')
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_-]*\$?', args.user):
        parser.error('Invalid account name')
    if not args.port.startswith('/dev/') or args.port.startswith(('/dev/ttyDWIN', '/dev/ttyS_DWIN')):
        parser.error('Select the physical display UART under /dev')
    quote(args.port)
    for path in (args.updater, args.asvc):
        if path and not path.resolve().is_relative_to(args.home.resolve()):
            parser.error('Moonraker registration must belong to the installed home')
    Path('/run/lock').mkdir(exist_ok=True)
    with open('/run/lock/petrel-dwin-install.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            Installer().apply(args.enabled == '1', args.repo, args.home, args.user, args.port, args.updater, args.asvc)
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
            detail = getattr(error, 'stderr', '') or str(error)
            parser.exit(1, 'DWIN UART configuration failed: ' + detail + '\n')


if __name__ == '__main__':
    main()
