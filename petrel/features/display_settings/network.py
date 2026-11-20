"""Host preferences for optional display background requests."""
from dataclasses import asdict, dataclass
import json
import logging
import os
from tempfile import NamedTemporaryFile

from petrel.features.notifications.store import notification_state_path


@dataclass(frozen=True)
class NetworkSettings:
    automatic_updates: bool = True
    project_announcements: bool = True

    @classmethod
    def load(cls, path=None):
        path = path if path is not None else preferences_path()
        try:
            values = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(values, dict):
                raise ValueError('Invalid network settings')
            defaults = asdict(cls())
            for key in defaults:
                value = values.get(key, defaults[key])
                if type(value) is not bool:
                    raise ValueError('Invalid network preference')
                defaults[key] = value
            return cls(**defaults)
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            logging.warning('Unable to read display network preferences', exc_info=True)
            return cls(automatic_updates=False, project_announcements=False)

    def save(self, path=None):
        path = path if path is not None else preferences_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                    prefix=f'.{path.name}.', delete=False) as stream:
                temporary = path.parent / os.path.basename(stream.name)
                json.dump(asdict(self), stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def preferences_path():
    return notification_state_path().with_name('display-network.json')
