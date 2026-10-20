#!/usr/bin/env python3
"""Reversible optional extra installation, called by existing configure.sh."""
import argparse
import fnmatch
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile

BEGIN = '# BEGIN Petrel axis travel (managed by configure.sh)'
END = '# END Petrel axis travel'
BLOCK = BEGIN+'\n[include petrel-axis-travel.cfg]\n'+END+'\n'
CONFIG = '# Managed by Petrel configure.sh; disable there.\n[petrel_axis_travel]\n'
EXCLUDE = '/klippy/extras/petrel_axis_travel.py'


def atomic(path, text):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.petrel-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write(text)
        if path.exists(): os.chmod(name,path.stat().st_mode & 0o777)
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def install(enabled, *, repo, klipper, printer_config, manifest):
    repo,klipper,printer_config,manifest = map(Path,(repo,klipper,printer_config,manifest))
    old = json.loads(manifest.read_text()) if manifest.exists() else None
    if old:
        if enabled and (str(klipper.resolve())!=old['klipper'] or str(printer_config.resolve())!=old['printer_config']):
            raise ValueError('Disable the existing installation before changing its paths.')
        klipper,printer_config = Path(old['klipper']),Path(old['printer_config'])
    elif not enabled:
        return False
    klipper,printer_config = klipper.resolve(),printer_config.resolve()
    target = klipper/'klippy/extras/petrel_axis_travel.py'
    source = (repo/'klipper_extras/petrel_axis_travel.py').resolve()
    fragment = printer_config.parent/'petrel-axis-travel.cfg'
    if not printer_config.is_file() or not target.parent.is_dir() or not source.is_file():
        raise ValueError('Klipper extras directory, printer.cfg or Petrel extra not found.')
    if os.path.lexists(target) and (not target.is_symlink() or target.resolve()!=source):
        raise ValueError('Refusing to replace a foreign Klipper extra.')
    tracked=subprocess.run(['git','-C',str(klipper),'ls-files','--error-unmatch',
                            'klippy/extras/petrel_axis_travel.py'],capture_output=True)
    if tracked.returncode==0:
        raise ValueError('Refusing to alter a tracked Klipper module.')
    if fragment.exists() and fragment.read_text()!=CONFIG:
        raise ValueError('Refusing to replace a foreign petrel-axis-travel.cfg.')
    if fragment.is_symlink():
        raise ValueError('Refusing a symlinked managed config fragment.')
    text = printer_config.read_text()
    if text.count(BEGIN)!=text.count(END) or text.count(BEGIN)>1:
        raise ValueError('Invalid managed config block; review printer.cfg.')
    if BEGIN in text:
        start=text.index(BEGIN);end=text.index(END,start)+len(END)
        if text[end:end+1]=='\n': end+=1
        clean=text[:start]+text[end:]
    else:
        clean=text
    if '[petrel_axis_travel]' in clean or '[include petrel-axis-travel.cfg]' in clean:
        raise ValueError('Existing unmanaged axis travel config; review before continuing.')
    exclude_name=subprocess.check_output(['git','-C',str(klipper),'rev-parse','--git-path','info/exclude'],text=True).strip()
    exclude=Path(exclude_name)
    if not exclude.is_absolute(): exclude=klipper/exclude
    excluded=exclude.read_text() if exclude.exists() else ''
    added = old['exclude_added'] if old else EXCLUDE not in excluded.splitlines()
    paths=(printer_config,fragment,exclude,manifest)
    backups={p:(p.read_bytes(),p.stat().st_mode & 0o777) if p.exists() else None for p in paths}
    linked=os.path.lexists(target)
    changed=False
    try:
        if enabled:
            if not linked:
                target.symlink_to(source);changed=True
            includes=re.findall(r'^\s*\[include\s+([^\]]+)\]\s*$',clean,re.MULTILINE)
            covered=any(fnmatch.fnmatch(fragment.name,pattern.strip()) for pattern in includes)
            desired=clean if covered else BLOCK+clean
            if text!=desired: atomic(printer_config,desired);changed=True
            if not fragment.exists(): atomic(fragment,CONFIG);changed=True
            if EXCLUDE not in excluded.splitlines():
                atomic(exclude,excluded+('' if not excluded or excluded.endswith('\n') else '\n')+EXCLUDE+'\n')
            atomic(manifest,json.dumps(dict(klipper=str(klipper),printer_config=str(printer_config),exclude_added=added)))
        else:
            if linked: target.unlink();changed=True
            if text!=clean: atomic(printer_config,clean);changed=True
            if fragment.exists(): fragment.unlink();changed=True
            if added:
                atomic(exclude,''.join(line for line in excluded.splitlines(keepends=True) if line.rstrip('\r\n')!=EXCLUDE))
            if manifest.exists(): manifest.unlink()
    except Exception:
        for path, backup in backups.items():
            if backup is None:
                if path.exists(): path.unlink()
            else:
                content,mode=backup
                fd,name=tempfile.mkstemp(dir=path.parent)
                with os.fdopen(fd,'wb') as stream: stream.write(content)
                os.chmod(name,mode);os.replace(name,path)
        if linked and not os.path.lexists(target): target.symlink_to(source)
        if not linked and os.path.lexists(target): target.unlink()
        raise
    return changed


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled',choices=('0','1'),required=True)
    for name in ('repo','klipper','printer-config','manifest'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:
        changed=install(args.enabled=='1',repo=args.repo,klipper=args.klipper,
                        printer_config=args.printer_config,manifest=args.manifest)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        parser.exit(1,'Axis travel configuration failed: '+str(exc)+'\n')
    if changed:
        print('Axis travel configuration changed. Restart Klipper while idle to apply it.')
        print('No Klipper restart was performed. Then restart Petrel to refresh discovery.')
