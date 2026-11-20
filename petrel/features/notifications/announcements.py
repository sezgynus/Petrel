"""Fetch the project's public announcements without blocking the display."""
from http.client import HTTPException
import json
import logging
import re
from time import monotonic
from urllib.request import Request, urlopen

from petrel.features.notifications.store import ANNOUNCEMENT_SOURCE, Notification
from petrel.printer.background_reads import ReadWorker


FEED_URL = 'https://raw.githubusercontent.com/sezgynus/Petrel/master/announcements.json'
FEED_INTERVAL = 3600
MAX_FEED_BYTES = 32 * 1024
MAX_ANNOUNCEMENTS = 64
ANNOUNCEMENT_ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}')


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
        entries[key] = Notification(ANNOUNCEMENT_SOURCE, key, title.strip(), detail.strip())
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

    def tick(self):
        if self._pending is not None:
            if not self._pending.done():
                return
            pending, self._pending = self._pending, None
            self._next_poll = monotonic() + FEED_INTERVAL
            try:
                self._store.sync_announcements(pending.result())
            except (OSError, ValueError, RuntimeError, HTTPException) as error:
                logging.debug('Project announcement sync skipped: %s', error)
            return
        if monotonic() >= self._next_poll:
            if self._worker is None:
                self._worker = ReadWorker(timeout=1, capacity=1, queue_timeout=5)
            self._pending = self._worker.submit(fetch_feed)

    def close(self):
        if self._pending is not None:
            self._pending.cancel()
        if self._worker is not None:
            self._worker.close()
