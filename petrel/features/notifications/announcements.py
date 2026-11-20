"""Fetch the project's public announcements without blocking the display."""
from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPException
import json
import logging
import re
from time import monotonic
from urllib.request import Request, urlopen

from petrel.features.notifications.store import ANNOUNCEMENT_SOURCE, Notification
from petrel.printer.background_reads import ReadWorker


FEED_URL = 'https://raw.githubusercontent.com/sezgynus/Petrel/master/announcements.json'
FEED_INTERVAL = 5 * 60
MAX_FEED_BYTES = 32 * 1024
MAX_ANNOUNCEMENTS = 64
ANNOUNCEMENT_ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}')

PUBLISH_AT = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?')


@dataclass(frozen=True)
class FeedAnnouncement:
    notification: Notification
    publish_at: datetime | None


def parse_feed(raw):
    data = json.loads(raw.decode('utf-8'))
    if (not isinstance(data, dict) or type(data.get('version')) is not int
            or data['version'] != 1 or not isinstance(data.get('announcements'), list)
            or len(data['announcements']) > MAX_ANNOUNCEMENTS):
        raise ValueError('Invalid announcement feed')
    entries = {}
    for item in data['announcements']:
        if not isinstance(item, dict):
            raise ValueError('Invalid announcement')
        key, title, detail = item.get('id'), item.get('title'), item.get('detail', '')
        if (not isinstance(key, str) or not ANNOUNCEMENT_ID.fullmatch(key) or key in entries
                or not isinstance(title, str) or not title.strip() or len(title) > 96
                or not isinstance(detail, str) or len(detail) > 256):
            raise ValueError('Invalid or duplicate announcement')
        publish_at = None
        if 'publish_at' in item:
            value = item['publish_at']
            if not isinstance(value, str) or not PUBLISH_AT.fullmatch(value):
                raise ValueError('Invalid local announcement time')
            publish_at = datetime.fromisoformat(value)
        entries[key] = FeedAnnouncement(
            Notification(ANNOUNCEMENT_SOURCE, key, title.strip(), detail.strip()), publish_at,
        )
    return tuple(entries.values())


def fetch_feed():
    request = Request(FEED_URL, headers={'Accept': 'application/json', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=5) as response:
        data = response.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError('Announcement feed exceeds size limit')
    return parse_feed(data)


class ProjectAnnouncements:
    def __init__(self, store):
        self._store = store
        self._worker = None
        self._pending = None
        self._next_poll = 0
        self._feed = ()
        self._next_release = None
        self._sync_pending = False
        self._retry_sync_at = 0
        self._discard_pending = False

    def tick(self, *, enabled=True):
        if not enabled:
            self._next_poll = 0
            self._feed = ()
            self._next_release = None
            self._sync_pending = False
            if self._pending is not None:
                self._pending.cancel()
                if self._pending.done():
                    self._pending = None
                    self._discard_pending = False
                else:
                    self._discard_pending = True
            return
        now = monotonic()
        if self._pending is not None and self._pending.done():
            pending, self._pending = self._pending, None
            if self._discard_pending:
                self._discard_pending = False
            else:
                self._next_poll = now + FEED_INTERVAL
                try:
                    self._feed = pending.result()
                except (OSError, ValueError, RuntimeError, HTTPException) as error:
                    logging.debug('Project announcement fetch skipped: %s', error)
                else:
                    self._sync_pending = True
                    self._retry_sync_at = now

        if self._sync_pending or self._next_release is not None:
            local_now = datetime.now()
            release_due = self._next_release is not None and local_now >= self._next_release
            if now >= self._retry_sync_at and (self._sync_pending or release_due):
                self._publish_due(local_now, now)

        if self._pending is None and now >= self._next_poll:
            if self._worker is None:
                self._worker = ReadWorker(timeout=1, capacity=1, queue_timeout=5)
            self._pending = self._worker.submit(fetch_feed)

    def _publish_due(self, local_now, now):
        visible = []
        scheduled_keys = set()
        next_release = None
        for item in self._feed:
            if item.publish_at is None or local_now >= item.publish_at:
                visible.append(item.notification)
            else:
                scheduled_keys.add(item.notification.key)
                if next_release is None or item.publish_at < next_release:
                    next_release = item.publish_at
        try:
            self._store.sync_announcements(visible, scheduled_keys=scheduled_keys)
        except OSError as error:
            logging.debug('Project announcement sync skipped: %s', error)
            self._sync_pending = True
            self._retry_sync_at = now + 5
        else:
            self._sync_pending = False
            self._next_release = next_release

    def close(self):
        if self._pending is not None:
            self._pending.cancel()
        if self._worker is not None:
            self._worker.close()
