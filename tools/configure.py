#!/usr/bin/env python3
"""Kconfig terminal frontend with explicit, reversible installation/apply."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import kconfiglib

# Make repository imports work when invoked as tools/configure.py from any cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.axis_travel_install import install as install_axis

BOOLS = {'PETREL_AXIS_TRAVEL', 'PETREL_EMULATOR', 'PETREL_REMOTE', 'PETREL_AUX_UART', 'PETREL_NFC', 'RESTART_PETREL'}
PATHS = {'PETREL_SETTINGS_FILE', 'PETREL_KLIPPER_DIR', 'PETREL_PRINTER_CONFIG'}
STRINGS = {'MOONRAKER_URL', 'PETREL_REQUEST_TIMEOUT', 'PETREL_SERIAL_PORT',
           'PETREL_POWER_DEVICE', 'PETREL_REMOTE_HOST'} | PATHS
BUZZER_GPIO_CHOICES = {'PETREL_BUZZER_GPIO12': 12, 'PETREL_BUZZER_GPIO13': 13,
                       'PETREL_BUZZER_GPIO18': 18, 'PETREL_BUZZER_GPIO19': 19}
INTS = {'ENCODER_A_GPIO': (0, 65535), 'ENCODER_B_GPIO': (0, 65535),
        'PETREL_BUTTON_PIN': (0, 65535), 'PETREL_POWER_ON_HOLD_MS': (0, 2147483647),
        'PETREL_REMOTE_PORT': (1, 65535)}
SYMBOLS = BOOLS | STRINGS | INTS.keys() | BUZZER_GPIO_CHOICES.keys()
RUNTIME = (SYMBOLS - BUZZER_GPIO_CHOICES.keys()
           - {'ENCODER_A_GPIO', 'ENCODER_B_GPIO', 'RESTART_PETREL'}) | {'PETREL_BUZZER_GPIO'}
MANAGED = RUNTIME | {'PETREL_ENCODER_PINS'}
ASSIGNMENT = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$', re.DOTALL)


def env_records(text):
    """Retain complete opaque assignments, including multiline private values."""
    lines = iter(text.splitlines(keepends=True))
    for line in lines:
        match = ASSIGNMENT.match(line)
        if not match:
            yield None, line, None
            continue
        key, value = match.groups()
        raw = line
        quoted = value.lstrip()[:1]
        if quoted in ('"', "'"):
            def closed(value):
                escaped = False
                for char in value.lstrip()[1:]:
                    if escaped:
                        escaped = False
                    elif char == '\\' and quoted == '"':
                        escaped = True
                    elif char == quoted:
                        return True
                return False
            while not closed(value):
                try:
                    extra = next(lines)
                except StopIteration:
                    raise ValueError('Unterminated quoted assignment: ' + key)
                raw += extra
                value += extra
        yield key, raw, value


def decode_env(value):
    value = value.strip()
    if value.startswith(('"', "'")):
        parts = shlex.split(value, comments=False, posix=True)
        if len(parts) != 1:
            raise ValueError('Invalid quoted setting')
        return parts[0]
    return value


def defaults(home):
    return dict(MOONRAKER_URL='http://127.0.0.1:7125', PETREL_REQUEST_TIMEOUT='5',
                PETREL_SERIAL_PORT='/dev/ttyS0', PETREL_POWER_DEVICE='Printer',
                PETREL_POWER_ON_HOLD_MS='2000', ENCODER_A_GPIO='21', ENCODER_B_GPIO='16', PETREL_BUZZER_GPIO='19',
                PETREL_BUTTON_PIN='20', PETREL_SETTINGS_FILE=str(home / '.config/Petrel/presets.json'),
                PETREL_AXIS_TRAVEL='y', PETREL_KLIPPER_DIR=str(home / 'klipper'),
                PETREL_PRINTER_CONFIG=str(home / 'printer_data/config/printer.cfg'),
                PETREL_EMULATOR='n', PETREL_REMOTE='n', PETREL_REMOTE_HOST='0.0.0.0',
                PETREL_REMOTE_PORT='8088', PETREL_AUX_UART='n', PETREL_NFC='n', RESTART_PETREL='y')


def normalize_bool(value):
    if value.lower() in ('1', 'true', 'yes', 'on', 'y'):
        return 'y'
    if value.lower() in ('0', 'false', 'no', 'off', 'n'):
        return 'n'
    raise ValueError('Boolean setting must be yes/no or 1/0')


def read_settings(home, text):
    values = defaults(home)
    for key, _, raw in env_records(text):
        if key not in MANAGED:
            continue  # Never decode or display opaque settings/API keys.
        value = decode_env(raw)
        if key == 'PETREL_ENCODER_PINS':
            pins = value.split()
            if len(pins) != 2:
                raise ValueError('PETREL_ENCODER_PINS requires two GPIO numbers')
            values['ENCODER_A_GPIO'], values['ENCODER_B_GPIO'] = pins
        else:
            values[key] = normalize_bool(value) if key in BOOLS else value
    return values


def collect(kconf):
    # user_value retains hidden paths/ports when their parent option is disabled.
    values = {name: (kconf.syms[name].str_value if name in BOOLS else
                     str(kconf.syms[name].user_value) if kconf.syms[name].user_value is not None
                     else kconf.syms[name].str_value)
              for name in SYMBOLS if name not in BUZZER_GPIO_CHOICES}
    selected = [pin for name, pin in BUZZER_GPIO_CHOICES.items()
                if kconf.syms[name].str_value == 'y']
    if len(selected) != 1:
        raise ValueError('Choose one hardware PWM buzzer GPIO')
    values['PETREL_BUZZER_GPIO'] = str(selected[0])
    return values


class Configuration(kconfiglib.Kconfig):
    def __init__(self, repo, values):
        super().__init__(str(repo / 'Kconfig'), warn_to_stderr=False)
        self.saved_values = None
        self.warn_assign_override = False
        self.warn_assign_redun = False
        for name, value in values.items():
            if name == 'PETREL_BUZZER_GPIO':
                continue
            if not self.syms[name].set_value(value):
                raise ValueError('Invalid existing setting: ' + name)
        pin = int(values['PETREL_BUZZER_GPIO'])
        matching = [name for name, candidate in BUZZER_GPIO_CHOICES.items()
                    if candidate == pin]
        if len(matching) != 1 or not self.syms[matching[0]].set_value('y'):
            raise ValueError('Unsupported hardware PWM buzzer GPIO')

    def write_config(self, filename=None, header=None, save_old=True, verbose=None):
        result = super().write_config(filename, header, save_old, verbose)
        self.saved_values = collect(self)
        return result


def config_text(values):
    """Full seed includes hidden preferences so toggling their parent restores them."""
    lines = []
    for name in sorted(SYMBOLS):
        value = ('y' if int(values['PETREL_BUZZER_GPIO']) == BUZZER_GPIO_CHOICES[name] else 'n') if name in BUZZER_GPIO_CHOICES else values[name]
        if name in STRINGS:
            value = '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
        lines.append('CONFIG_' + name + '=' + value + '\n')
    return ''.join(lines)


def validate(values):
    for key, value in values.items():
        if any(char in value for char in ('\x00', '\n', '\r')):
            raise ValueError(key + ' must be a single-line value')
    for name in BOOLS:
        if values[name] not in ('y', 'n'):
            raise ValueError('Invalid boolean: ' + name)
    for name, (low, high) in INTS.items():
        if not re.fullmatch(r'[0-9]+', values[name]) or not low <= int(values[name]) <= high:
            raise ValueError(f'{name} must be {low}..{high}')
    pins = [values[k] for k in ('ENCODER_A_GPIO', 'ENCODER_B_GPIO', 'PETREL_BUTTON_PIN')]
    if len(set(map(int, pins))) != 3:
        raise ValueError('Encoder A, B and button GPIOs must differ')
    if (not re.fullmatch(r'[0-9]+', values['PETREL_BUZZER_GPIO']) or
            int(values['PETREL_BUZZER_GPIO']) not in BUZZER_GPIO_CHOICES.values()):
        raise ValueError('Buzzer GPIO must support hardware PWM: 12, 13, 18 or 19')
    if int(values['PETREL_BUZZER_GPIO']) in set(map(int, pins)):
        raise ValueError('Buzzer GPIO must differ from encoder A/B and button GPIOs')
    url = urlsplit(values['MOONRAKER_URL'])
    if url.scheme not in ('http', 'https') or not url.hostname:
        raise ValueError('Moonraker URL must be an HTTP(S) address')
    timeout = float(values['PETREL_REQUEST_TIMEOUT'])
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Request timeout must be positive')
    if not values['PETREL_SERIAL_PORT'].startswith('/dev/') or values['PETREL_SERIAL_PORT'].startswith(('/dev/ttyDWIN', '/dev/ttyS_DWIN')):
        raise ValueError('Select the physical display UART under /dev')
    for name in PATHS:
        if not Path(values[name]).is_absolute():
            raise ValueError(name + ' must be an absolute path')
    if values['PETREL_REMOTE'] == 'y' and not values['PETREL_REMOTE_HOST'].strip():
        raise ValueError('Remote bind address cannot be empty')


def render_env(values, original):
    result = '# Petrel runtime configuration.\n# Generated by configure.sh (Kconfig).\n'
    # Keep foreign lines and private API-key records byte-for-byte.
    opaque = ''.join(raw for key, raw, _ in env_records(original)
                     if key not in MANAGED and not raw.startswith(('# Petrel runtime configuration.', '# Generated by configure.sh')))
    for name in sorted(RUNTIME):
        value = values[name]
        if name in BOOLS:
            encoded = '1' if value == 'y' else '0'
        elif name in INTS or name == 'PETREL_BUZZER_GPIO':
            encoded = value
        else:
            encoded = '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
        result += name + '=' + encoded + '\n'
    result += 'PETREL_ENCODER_PINS="' + values['ENCODER_A_GPIO'] + ' ' + values['ENCODER_B_GPIO'] + '"\n'
    if opaque:
        result += opaque
        if not result.endswith('\n'):
            result += '\n'
    return result


def atomic_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.petrel-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def command(*args):
    return subprocess.run(list(map(str, args)), check=True, text=True, capture_output=True)


def dwin_install(repo, home, user, enabled, port):
    result = command('sudo', 'python3', repo / 'tools/dwin_uart_install.py',
                     '--enabled', '1' if enabled else '0', '--repo', repo,
                     '--home', home, '--user', user, '--port', port)
    if result.stdout:
        print(result.stdout, end='')


def nfc_install(repo, enabled):
    result = command('sudo', 'python3', repo / 'tools/nfc_install.py',
                     '--enabled', '1' if enabled else '0')
    if result.stdout:
        print(result.stdout, end='')


def pwm_install(repo, user, pin):
    result = command('sudo', 'python3', repo / 'tools/pwm_install.py',
                     '--install', '--repo', repo, '--user', user, '--pin', pin)
    if result.stdout:
        print(result.stdout, end='')


def apply(values, *, repo, home, user, original, axis=install_axis, dwin=dwin_install,
          nfc=nfc_install, pwm=None, writer=atomic_private,
          dwin_manifest=Path('/var/lib/Petrel/dwin-uart.json'),
          nfc_manifest=Path('/var/lib/Petrel/nfc.json')):
    validate(values)
    env_file = home / '.config/Petrel/Petrel.env'
    if (env_file.read_text() if env_file.exists() else '') != original:
        raise ValueError('Settings changed while the menu was open; reopen configure.sh')
    previous = read_settings(home, original)
    axis_manifest = home / '.config/Petrel/axis-travel-install.json'
    old_axis = json.loads(axis_manifest.read_text()) if axis_manifest.exists() else None
    old_dwin = json.loads(dwin_manifest.read_text()) if dwin_manifest.exists() else None
    old_nfc = json.loads(nfc_manifest.read_text()) if nfc_manifest.exists() else None
    axis_done = dwin_done = nfc_done = pwm_done = False
    try:
        changed = axis(values['PETREL_AXIS_TRAVEL'] == 'y', repo=repo,
                       klipper=values['PETREL_KLIPPER_DIR'], printer_config=values['PETREL_PRINTER_CONFIG'],
                       manifest=axis_manifest)
        axis_done = True
        if values['PETREL_AUX_UART'] == 'y' or previous['PETREL_AUX_UART'] == 'y' or old_dwin:
            dwin(repo, home, user, values['PETREL_AUX_UART'] == 'y', values['PETREL_SERIAL_PORT'])
            dwin_done = True
        if values['PETREL_NFC'] == 'y' or previous['PETREL_NFC'] == 'y' or old_nfc:
            nfc(repo, values['PETREL_NFC'] == 'y')
            nfc_done = True
        if pwm is not None:
            pwm(repo, user, values['PETREL_BUZZER_GPIO'])
            pwm_done = True
        writer(env_file, render_env(values, original))
    except Exception:
        # Each installer rolls its own failure back; undo earlier successful steps.
        if pwm_done:
            try:
                pwm(repo, user, previous['PETREL_BUZZER_GPIO'])
            except Exception as error:
                print('PWM rollback needs attention: ' + str(error), file=sys.stderr)
        if dwin_done:
            try:
                dwin(repo, home, user, bool(old_dwin), old_dwin['port'] if old_dwin else previous['PETREL_SERIAL_PORT'])
            except Exception as error:
                print('DWIN rollback needs attention: ' + str(error), file=sys.stderr)
        if nfc_done:
            try:
                nfc(repo, bool(old_nfc and old_nfc.get('enabled')))
            except Exception as error:
                print('NFC rollback needs attention: ' + str(error), file=sys.stderr)
        if axis_done:
            try:
                axis(bool(old_axis), repo=repo,
                     klipper=old_axis['klipper'] if old_axis else values['PETREL_KLIPPER_DIR'],
                     printer_config=old_axis['printer_config'] if old_axis else values['PETREL_PRINTER_CONFIG'],
                     manifest=axis_manifest)
            except Exception as error:
                print('Counter rollback needs attention: ' + str(error), file=sys.stderr)
        raise
    if changed:
        print('Counter configuration changed. Restart Klipper manually while idle; no Klipper restart was performed.')
    print('Configuration applied: ' + str(env_file))


@contextmanager
def menu_environment(config_path):
    names = {'KCONFIG_CONFIG': str(config_path), 'KCONFIG_CONFIG_HEADER': '', 'KCONFIG_OVERWRITECONFIG': '1'}
    old = {key: os.environ.get(key) for key in names}
    os.environ.update(names)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def choose(kconf, values, launch=None, confirm=None):
    if launch is None:
        from menuconfig import menuconfig
        launch = menuconfig
    if confirm is None:
        confirm = input
    with tempfile.TemporaryDirectory(prefix='petrel-config-') as directory:
        seed = Path(directory) / 'selection.config'
        seed.write_text(config_text(values))
        seed.chmod(0o600)
        with menu_environment(seed):
            launch(kconf)
        if kconf.saved_values is None:
            print('Configuration cancelled; no installation or settings changes.')
            return None
        answer = confirm('Apply saved configuration and selected installations? [y/N]: ')
        if answer.strip().lower() not in ('y', 'yes'):
            print('Configuration cancelled; no installation or settings changes.')
            return None
        return kconf.saved_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--user', required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply-config', type=Path, help='Apply an explicit Kconfig .config without opening a menu')
    modes.add_argument('--export-config', type=Path, help='Export existing settings in Kconfig format without applying')
    parser.add_argument('--no-restart', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    env_file = args.home / '.config/Petrel/Petrel.env'
    try:
        original = env_file.read_text() if env_file.exists() else ''
        values = read_settings(args.home, original)
        kconf = Configuration(args.repo, values)
        if args.export_config:
            atomic_private(args.export_config, config_text(values))
            return 0
        if args.apply_config:
            kconf.load_config(str(args.apply_config), replace=False)
            if kconf.warnings or kconf.missing_syms:
                raise ValueError('Invalid or unknown settings in the supplied Kconfig file')
            selected = collect(kconf)
        else:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ValueError('A terminal is required. Use --apply-config FILE for explicit unattended configuration.')
            print('Space: toggle | Enter: edit/menu | ?: help | S: save | Q: quit. Saving alone does not apply.')
            selected = choose(kconf, values)
            if selected is None:
                return 2
        validate(selected)
        config_dir = env_file.parent
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (config_dir / 'configure.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            apply(selected, repo=args.repo, home=args.home, user=args.user,
                  original=original, pwm=pwm_install)
        if not args.no_restart and selected['RESTART_PETREL'] == 'y':
            active = subprocess.run(['systemctl', 'is-active', '--quiet', 'Petrel.service'], capture_output=True)
            if active.returncode == 0:
                command('sudo', 'systemctl', 'restart', 'Petrel.service')
                print('Petrel.service restarted.')
        return 0
    except (OSError, ValueError, kconfiglib.KconfigError, subprocess.SubprocessError) as error:
        detail = getattr(error, 'stderr', '') or str(error)
        parser.exit(1, 'Petrel configuration failed: ' + detail + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
