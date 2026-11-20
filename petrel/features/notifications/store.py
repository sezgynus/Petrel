"""Source-independent notification state and lifecycle."""
from dataclasses import dataclass
from enum import Enum
from threading import Lock


class Retention(Enum):
    DISMISSIBLE = 'dismissible'
    UNTIL_RESOLVED = 'until_resolved'


@dataclass(frozen=True)
class Notification:
    source: str
    key: str
    title: str
    detail: str = ''
    retention: Retention = Retention.DISMISSIBLE
    action: str | None = None

    @property
    def identity(self):
        return self.source, self.key


class NotificationStore:
    """Thread-safe feed. Repeated publications update the same source/key."""

    def __init__(self):
        self._lock = Lock()
        self._entries = {}
        self._revision = 0

    def snapshot(self):
        with self._lock:
            return self._revision, tuple(reversed(self._entries.values()))

    def publish(self, notification):
        with self._lock:
            if self._entries.get(notification.identity) == notification:
                return False
            self._entries[notification.identity] = notification
            self._revision += 1
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
        del self._entries[identity]
        self._revision += 1
        return True
