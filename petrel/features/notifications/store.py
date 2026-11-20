"""Source-independent notification state and lifecycle."""
from dataclasses import asdict, dataclass
from enum import Enum
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock


class Retention(Enum):
    DISMISSIBLE = 'dismissible'
    UNTIL_RESOLVED = 'until_resolved'


class Persistence(Enum):
    PERSISTENT = 'persistent'
    VOLATILE = 'volatile'


def notification_state_path():
    root = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return root / 'Petrel' / 'notifications.json'


@dataclass(frozen=True)
class Notification:
    source: str
    key: str
    title: str
    detail: str = ''
    retention: Retention = Retention.DISMISSIBLE
    action: str | None = None
    persistence: Persistence = Persistence.PERSISTENT

    @property
    def identity(self):
        return self.source, self.key


class NotificationStore:
    """Thread-safe feed. Repeated publications update the same source/key."""

    def __init__(self, path=None):
        self._lock = Lock()
        self._path = Path(path) if path is not None else None
        self._read_error = None
        self._entries = self._load()
        self._revision = 0

    def snapshot(self):
        with self._lock:
            return self._revision, tuple(reversed(self._entries.values()))

    def publish(self, notification):
        with self._lock:
            previous = self._entries.get(notification.identity)
            if previous == notification:
                return False
            entries = dict(self._entries)
            entries[notification.identity] = notification
            self._commit(entries, self._persistent(previous) or self._persistent(notification))
            return True

    def dismiss(self, notification):
        with self._lock:
            current = self._entries.get(notification.identity)
            if current != notification or current.retention is not Retention.DISMISSIBLE:
                return False
            return self._remove(notification.identity)

    def resolve(self, source, key):
        with self._lock:
            return self._remove((source, key))

    def _remove(self, identity):
        if identity not in self._entries:
            return False
        entries = dict(self._entries)
        removed = entries.pop(identity)
        self._commit(entries, self._persistent(removed))
        return True

    @staticmethod
    def _persistent(notification):
        return notification is not None and notification.persistence is Persistence.PERSISTENT

    def _commit(self, entries, persist):
        if persist and self._path is not None:
            if self._read_error is not None:
                raise OSError(f'Cannot update unreadable notification state: {self._path}') from self._read_error
            self._save(entries)
        self._entries = entries
        self._revision += 1

    def _load(self):
        if self._path is None:
            return {}
        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1:
                raise ValueError('Unsupported notification state version')
            if not isinstance(data.get('entries'), list):
                raise ValueError('Invalid notification state entries')
            entries = {}
            for item in data['entries']:
                record = Notification(
                    source=item['source'], key=item['key'], title=item['title'],
                    detail=item['detail'], retention=Retention(item['retention']),
                    action=item['action'],
                )
                if (not all(isinstance(value, str) for value in
                            (record.source, record.key, record.title, record.detail))
                        or (record.action is not None and not isinstance(record.action, str))):
                    raise ValueError('Invalid notification field')
                entries[record.identity] = record
            return entries
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, KeyError) as error:
            self._read_error = error
            logging.warning('Cannot load notification state %s: %s', self._path, error)
            return {}

    def _save(self, entries):
        records = []
        for item in entries.values():
            if self._persistent(item):
                record = asdict(item)
                record['retention'] = item.retention.value
                del record['persistence']
                records.append(record)
        path = self._path
        existing_parent = path.parent
        while existing_parent != existing_parent.parent and not existing_parent.exists():
            existing_parent = existing_parent.parent
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                    prefix=f'.{path.name}.', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'version': 1, 'entries': records}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        # Sync the rename as well as the file data on the Raspberry Pi.
        if os.name == 'posix':
            directory = path.parent
            while True:
                try:
                    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                except OSError:
                    logging.exception('Cannot sync notification state directory %s', directory)
                if directory == existing_parent:
                    break
                directory = directory.parent
