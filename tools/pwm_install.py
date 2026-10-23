#!/usr/bin/env python3
"""Install Petrel's BCM2835 PWM boot mapping and a narrow systemd access helper.

The daemon itself remains an unprivileged service. Only its dedicated PWM
channel attributes become writable by that account; no general root access.
"""
import argparse
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile
import time

PINS = {12: (0, 4), 13: (1, 4), 18: (0, 2), 19: (1, 2)}
BEGIN = '# BEGIN PETREL HARDWARE PWM'
END = '# END PETREL HARDWARE PWM'


def mapping(line):
    args = line.strip().split(',')
    if not args or not args[0].startswith('dtoverlay=pwm'):
        return {}
    name = args[0].split('=', 1)[1]
    if name not in ('pwm', 'pwm-2chan'):
        return {}
    items = dict(part.split('=', 1) for part in args[1:] if '=' in part)
    channels = {0: (int(items.get('pin', '18')), int(items.get('func', '2')))}
    if name == 'pwm-2chan':
        channels[1] = (int(items.get('pin2', '19')), int(items.get('func2', '2')))
    elif channels[0][0] in (13, 19):
        channels = {1: channels[0]}
    return channels


def render_boot(existing, gpio):
    if gpio not in PINS:
        raise ValueError('Unsupported hardware PWM GPIO')
    without = existing
    if BEGIN in without:
        if without.count(BEGIN) != 1 or without.count(END) != 1:
            raise ValueError('Malformed managed PWM boot section')
        start, finish = without.index(BEGIN), without.index(END) + len(END)
        without = without[:start] + without[finish:]
    # Do not overwrite a user's own PWM device-tree overlays. Reuse a
    # compatible one, reject a conflicting one instead of stealing its pin.
    outside = [line for line in without.splitlines()
               if re.match(r'^\s*dtoverlay=pwm(?:-2chan)?(?:,|\s|$)', line)]
    expected_channel, expected_func = PINS[gpio]
    if outside:
        if len(outside) != 1:
            raise ValueError('Multiple user PWM overlays; resolve them manually')
        configured = mapping(outside[0])
        if configured.get(expected_channel) != (gpio, expected_func):
            raise ValueError('Existing non-Petrel PWM overlay conflicts with buzzer GPIO')
        overlay = ''
    else:
        overlay = 'dtoverlay=pwm,pin=%d,func=%d\n' % (gpio, expected_func)
    block = '\n'.join((BEGIN, '[all]', 'dtparam=audio=off', overlay.rstrip('\n'), END)).replace('\n\n' + END, '\n' + END)
    return without.rstrip('\n') + '\n\n' + block + '\n'


def atomic(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.petrel-pwm-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def boot_config():
    primary = Path('/boot/firmware/config.txt')
    return primary if primary.exists() else Path('/boot/config.txt')


def install(repo, user, gpio):
    config = boot_config()
    before = config.read_text()
    after = render_boot(before, gpio)
    dropin = Path('/etc/systemd/system/Petrel.service.d/50-hardware-pwm.conf')
    repo = Path(repo).resolve()
    # ExecStartPre runs with root privileges. Never execute scripts from a
    # user-writable home directory under root on every service restart.
    script = Path('/usr/local/libexec/petrel-pwm-helper')
    source = (repo / 'tools/pwm_install.py').read_text()
    if not script.exists() or script.read_text() != source:
        atomic(script, source, mode=0o755)
    os.chown(script, 0, 0)
    # EnvironmentFile is read by systemd before ExecStartPre.
    dropin_text = ('# Petrel managed hardware PWM setup\n'
                   '[Service]\n'
                   'ExecStartPre=+/usr/bin/python3 ' + str(script) + ' --prepare --pin ${PETREL_BUZZER_GPIO} --user ' + user + '\n'
                   'ExecStopPost=+/usr/bin/python3 ' + str(script) + ' --stop --pin ${PETREL_BUZZER_GPIO} --user ' + user + '\n')
    if dropin.exists() and not dropin.read_text().startswith('# Petrel managed hardware PWM setup\n'):
        raise ValueError('Refusing to overwrite unmanaged systemd drop-in')
    if after != before:
        backup = config.with_name(config.name + '.petrel-pwm.bak')
        if not backup.exists():
            atomic(backup, before, mode=0o600)
        atomic(config, after)
        print('PWM boot overlay updated; reboot required before hardware audio works.')
    if not dropin.exists() or dropin.read_text() != dropin_text:
        atomic(dropin, dropin_text)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)


def gpio_is_pwm(gpio):
    tool = '/usr/bin/pinctrl'
    if not Path(tool).exists():
        tool = '/usr/bin/raspi-gpio'
    if not Path(tool).exists():
        return True   # The sysfs driver's presence is the fallback check.
    result = subprocess.run([tool, 'get', str(gpio)], capture_output=True, text=True)
    return result.returncode == 0 and 'PWM' in result.stdout.upper()


def find_chip(root=Path('/sys/class/pwm')):
    candidates = []
    for chip in sorted(root.glob('pwmchip*')):
        try:
            if int((chip / 'npwm').read_text()) >= 2:
                candidates.append(chip)
        except (OSError, ValueError):
            pass
    bcm = [path for path in candidates if ('3f20c000.pwm' in str(path.resolve())
                                          or 'fe20c000.pwm' in str(path.resolve()))]
    if len(bcm) == 1:
        return bcm[0]
    if len(candidates) == 1:
        return candidates[0]
    raise OSError('BCM2835 hardware PWM sysfs device not uniquely available')


def channel_dir(gpio):
    chip = find_chip()
    channel = PINS[gpio][0]
    path = chip / ('pwm' + str(channel))
    return chip, channel, path


def prepare(gpio, user):
    if not gpio_is_pwm(gpio):
        print('PWM pinmux not active; reboot is required', file=sys.stderr)
        return
    try:
        chip, channel, path = channel_dir(gpio)
    except OSError as error:
        print('PWM driver unavailable: ' + str(error), file=sys.stderr)
        return
    created = False
    if not path.exists():
        (chip / 'export').write_text(str(channel))
        created = True
        for _ in range(40):
            if path.exists():
                break
            time.sleep(.025)
    if not path.exists():
        print('PWM export failed', file=sys.stderr)
        return
    uid = pwd.getpwnam(user).pw_uid
    gid = pwd.getpwnam(user).pw_gid
    # Never take ownership of a channel already in use by a different user.
    if not created and (path / 'enable').stat().st_uid not in (0, uid):
        print('PWM channel owned by another process', file=sys.stderr)
        return
    if not created and (path / 'enable').stat().st_uid == 0:
        print('PWM channel already exported externally; not claiming', file=sys.stderr)
        return
    for name in ('period', 'duty_cycle', 'enable'):
        target = path / name
        if created:
            os.chown(target, uid, gid)
            os.chmod(target, 0o600)
    if created:
        (path / 'enable').write_text('0')
        (path / 'duty_cycle').write_text('0')


def stop(gpio, user):
    try:
        _, _, path = channel_dir(gpio)
        if (path / 'enable').stat().st_uid != pwd.getpwnam(user).pw_uid:
            return
        (path / 'enable').write_text('0')
        (path / 'duty_cycle').write_text('0')
    except (OSError, ValueError):
        pass


def main():
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--install', action='store_true')
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--stop', action='store_true')
    p.add_argument('--repo', type=Path)
    p.add_argument('--pin', type=int, required=True, choices=PINS)
    p.add_argument('--user', required=True)
    args = p.parse_args()
    if args.install:
        if args.repo is None:
            p.error('--repo required for --install')
        install(args.repo, args.user, args.pin)
    elif args.prepare:
        try:
            prepare(args.pin, args.user)
        except (OSError, ValueError, KeyError) as error:
            # Audio is optional. Never block Petrel.service startup because a
            # channel is unavailable, busy, or sysfs ownership cannot change.
            print('Hardware PWM buzzer disabled: ' + str(error), file=sys.stderr)
    else:
        stop(args.pin, args.user)


if __name__ == '__main__':
    main()
