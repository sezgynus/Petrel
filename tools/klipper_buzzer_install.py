#!/usr/bin/env python3
"""Reversible optional virtual Klipper SET_PIN buzzer module installation.

Mirrors Petrel's axis-travel managed-extra policy: preserve foreign files,
untracked Git excludes, existing includes, and third-party Klipper sources.
"""
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

BEGIN = '# BEGIN Petrel virtual buzzer (managed by configure.sh)'
END = '# END Petrel virtual buzzer'
BLOCK = BEGIN + '\n[include petrel-buzzer.cfg]\n' + END + '\n'
EXCLUDE = '/klippy/extras/petrel_buzzer.py'


def config_text(home):
    path = Path(home).resolve() / '.config/Petrel/klipper-buzzer.sock'
    return ('# Managed by Petrel configure.sh; disable in its Kconfig menu.\n'
            '[petrel_buzzer Buzzer]\n'
            'socket_path: %s\n'
            'value: 0\nshutdown_value: 0\ncycle_time: 0.001\n' % path)


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.petrel-buzzer-')
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(content)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def install(enabled, *, repo, klipper, printer_config, manifest, home):
    repo, klipper, printer_config, manifest, home = map(
        Path, (repo, klipper, printer_config, manifest, home))
    old = json.loads(manifest.read_text()) if manifest.exists() else None
    if old:
        if enabled and (str(klipper.resolve()) != old['klipper']
                        or str(printer_config.resolve()) != old['printer_config']):
            raise ValueError('Disable the existing virtual buzzer before changing its paths')
        klipper, printer_config = Path(old['klipper']), Path(old['printer_config'])
    elif not enabled:
        return False

    klipper, printer_config = klipper.resolve(), printer_config.resolve()
    source = (repo / 'klipper_extras/petrel_buzzer.py').resolve()
    target = klipper / 'klippy/extras/petrel_buzzer.py'
    fragment = printer_config.parent / 'petrel-buzzer.cfg'
    expected = config_text(home)
    if not (printer_config.is_file() and target.parent.is_dir() and source.is_file()):
        raise ValueError('Klipper extras path, printer.cfg or Petrel buzzer source missing')
    if os.path.lexists(target) and (not target.is_symlink() or target.resolve() != source):
        raise ValueError('Refusing to replace a foreign Klipper buzzer module')
    tracked = subprocess.run(['git', '-C', str(klipper), 'ls-files',
                              '--error-unmatch', 'klippy/extras/petrel_buzzer.py'],
                             capture_output=True)
    if tracked.returncode == 0:
        raise ValueError('Refusing to modify a tracked Klipper module')
    if fragment.is_symlink() or (fragment.exists() and fragment.read_text() != expected):
        raise ValueError('Refusing to replace foreign petrel-buzzer.cfg')
    content = printer_config.read_text()
    if content.count(BEGIN) != content.count(END) or content.count(BEGIN) > 1:
        raise ValueError('Invalid managed virtual buzzer config block')
    if BEGIN in content:
        start = content.index(BEGIN)
        end = content.index(END, start) + len(END)
        if content[end:end+1] == '\n':
            end += 1
        cleaned = content[:start] + content[end:]
    else:
        cleaned = content
    if (re.search(r'(?im)^\s*\[petrel_buzzer\s+Buzzer\s*\]', cleaned)
            or re.search(r'(?im)^\s*\[include\s+petrel-buzzer\.cfg\s*\]', cleaned)):
        raise ValueError('Unmanaged Petrel virtual buzzer config exists')
    exclude_file = subprocess.check_output(
        ['git','-C',str(klipper),'rev-parse','--git-path','info/exclude'],
        text=True).strip()
    exclude = Path(exclude_file)
    if not exclude.is_absolute():
        exclude = klipper / exclude
    previous_exclude = exclude.read_text() if exclude.exists() else ''
    added = old['exclude_added'] if old else EXCLUDE not in previous_exclude.splitlines()
    tracked_paths = (printer_config, fragment, exclude, manifest)
    backups = {p: (p.read_bytes(), p.stat().st_mode & 0o777)
               if p.exists() else None for p in tracked_paths}
    was_linked = os.path.lexists(target)
    changed = False
    try:
        if enabled:
            if not was_linked:
                target.symlink_to(source)
                changed = True
            includes = re.findall(r'^\s*\[include\s+([^\]]+)\]\s*$',
                                  cleaned, re.MULTILINE)
            covered = any(fnmatch.fnmatch(fragment.name, pat.strip()) for pat in includes)
            desired = cleaned if covered else BLOCK + cleaned
            if content != desired:
                atomic(printer_config, desired)
                changed = True
            if not fragment.exists():
                atomic(fragment, expected)
                changed = True
            if EXCLUDE not in previous_exclude.splitlines():
                atomic(exclude, previous_exclude +
                       ('' if not previous_exclude or previous_exclude.endswith('\n') else '\n')
                       + EXCLUDE + '\n')
            atomic(manifest, json.dumps(dict(
                klipper=str(klipper), printer_config=str(printer_config),
                exclude_added=added)))
        else:
            if was_linked:
                target.unlink()
                changed = True
            if content != cleaned:
                atomic(printer_config, cleaned)
                changed = True
            if fragment.exists():
                fragment.unlink()
                changed = True
            if added:
                atomic(exclude, ''.join(line for line in previous_exclude.splitlines(
                    keepends=True) if line.rstrip('\r\n') != EXCLUDE))
            if manifest.exists():
                manifest.unlink()
    except Exception:
        for path, backup in backups.items():
            if backup is None:
                if path.exists():
                    path.unlink()
            else:
                data, mode = backup
                fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.petrel-buzzer-')
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                os.chmod(tmp, mode)
                os.replace(tmp, path)
        if was_linked and not os.path.lexists(target):
            target.symlink_to(source)
        if not was_linked and os.path.lexists(target):
            target.unlink()
        raise
    return changed
