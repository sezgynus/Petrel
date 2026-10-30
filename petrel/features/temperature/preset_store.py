"""Versioned local presets with validated reads and atomic replacement."""
import json
import math
import os
from pathlib import Path
import tempfile


def default_path():
    root = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(root) / 'Petrel' / 'presets.json'


class PresetStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_path()

    @staticmethod
    def validate(document):
        if not isinstance(document, dict) or document.get('version') != 1:
            raise ValueError('Unsupported preset file version')
        presets = document.get('presets')
        if not isinstance(presets, list) or len(presets) != 2:
            raise ValueError('Expected PLA and ABS presets')
        for preset, name in zip(presets, ('PLA', 'ABS')):
            if not isinstance(preset, dict) or preset.get('name') != name:
                raise ValueError('Invalid preset name')
            for key in ('hotend_temp', 'bed_temp'):
                value = preset.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError('Invalid preset value: ' + key)
        return presets

    def load(self):
        try:
            with self.path.open(encoding='utf-8') as stream:
                return self.validate(json.load(stream))
        except FileNotFoundError:
            return None

    def save(self, presets):
        document = {'version': 1, 'presets': presets}
        self.validate(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=self.path.parent, delete=False) as stream:
                temporary = stream.name
                json.dump(document, stream, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
