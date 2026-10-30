"""One cached installed-source version for client identification; no hot-path I/O."""
from functools import lru_cache
from pathlib import Path
import re
import subprocess


@lru_cache(maxsize=1)
def client_version():
    try:
        result = subprocess.run(['git', '-C', str(Path(__file__).resolve().parents[1]),
                                 'describe', '--tags', '--always', '--dirty'],
                                capture_output=True, text=True, timeout=1, check=True)
        value = result.stdout.strip()
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+/-]{0,127}', value):
            return value
    except (OSError, subprocess.SubprocessError, UnicodeError):
        pass
    return 'unknown'
