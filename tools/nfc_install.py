#!/usr/bin/env python3
"""Manage Petrel's optional libnfc runtime package."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

PACKAGE = 'libnfc6'
DEFAULT_MANIFEST = Path('/var/lib/Petrel/nfc.json')


def run(*args, check=True):
    return subprocess.run(list(map(str, args)), check=check, text=True,
                          capture_output=True)


def package_installed(execute=run):
    result = execute('dpkg-query', '-W', '-f=${db:Status-Status}', PACKAGE, check=False)
    return result.returncode == 0 and result.stdout.strip() == 'installed'


def write_manifest(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.nfc-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, sort_keys=True)
            stream.write('\n')
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(enabled, *, manifest=DEFAULT_MANIFEST, execute=run):
    manifest = Path(manifest)
    previous = json.loads(manifest.read_text()) if manifest.exists() else None
    if enabled:
        was_installed = package_installed(execute)
        if not was_installed:
            execute('apt-get', 'update')
            execute('apt-get', 'install', '-y', PACKAGE)
        try:
            write_manifest(manifest, {
                'enabled': True,
                'package': PACKAGE,
                'installed_by_petrel': bool(
                    (previous and previous.get('installed_by_petrel')) or not was_installed),
            })
        except Exception:
            if not was_installed:
                execute('apt-get', 'remove', '-y', PACKAGE, check=False)
            raise
        return

    if previous and previous.get('installed_by_petrel') and package_installed(execute):
        execute('apt-get', 'remove', '-y', PACKAGE)
    if manifest.exists():
        manifest.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', choices=('0', '1'), required=True)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    install(args.enabled == '1', manifest=args.manifest)


if __name__ == '__main__':
    main()
