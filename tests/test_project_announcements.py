import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock

from petrel.features.notifications.announcements import ProjectAnnouncements, parse_feed
from petrel.features.notifications.store import NotificationStore


def feed(*ids):
    raw = {'version': 1, 'announcements': [{'id': key, 'title': key} for key in ids]}
    return parse_feed(json.dumps(raw).encode())


class ProjectAnnouncementTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / 'notifications.json'
        self.store = NotificationStore(self.path)

    def test_read_id_is_durable_and_pruned_only_when_absent(self):
        self.store.sync_announcements(feed('first', 'second'))
        self.assertTrue(self.store.dismiss(self.store.snapshot()[1][1]))
        restored = NotificationStore(self.path)
        restored.sync_announcements(feed('first', 'second'))
        self.assertEqual(tuple(item.key for item in restored.snapshot()[1]), ('second',))
        self.assertEqual(json.loads(self.path.read_text())['read_announcements'], ['first'])
        restored.sync_announcements(feed())
        self.assertEqual(tuple(item.key for item in restored.snapshot()[1]), ('second',))
        self.assertNotIn('read_announcements', json.loads(self.path.read_text()))
        self.assertTrue(restored.dismiss(restored.snapshot()[1][0]))
        self.assertNotIn('read_announcements', json.loads(self.path.read_text()))

    def test_invalid_refresh_does_not_prune_read_ids(self):
        self.store.sync_announcements(feed('first'))
        self.store.dismiss(self.store.snapshot()[1][0])
        poller = ProjectAnnouncements(self.store)
        poller._worker = Mock()
        pending = Future()
        pending.set_exception(ValueError('Invalid feed'))
        poller._worker.submit.return_value = pending
        poller.tick()
        poller.tick()
        poller.tick()
        poller._worker.submit.assert_called_once()
        self.assertEqual(json.loads(self.path.read_text())['read_announcements'], ['first'])

    def test_invalid_or_duplicate_entries_reject_entire_feed(self):
        with self.assertRaises(ValueError):
            feed('first', 'first')
        for raw in (b'{}', b'{"version":1,"announcements":[{"id":"x"}]}'):
            with self.assertRaises(ValueError):
                parse_feed(raw)
