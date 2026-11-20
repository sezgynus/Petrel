import json
import tempfile
import unittest
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from petrel.features.notifications.announcements import ProjectAnnouncements, parse_feed
from petrel.features.notifications.store import NotificationStore


def feed(*ids):
    raw = {'version': 1, 'announcements': [{'id': key, 'title': key} for key in ids]}
    return tuple(item.notification for item in parse_feed(json.dumps(raw).encode()))


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

    def test_scheduled_announcement_appears_at_local_time_without_refetching(self):
        raw = (b'{"version":1,"announcements":['
               b'{"id":"new-year","title":"New year","publish_at":"2027-01-01T12:00"},'
               b'{"id":"now","title":"Now"}]}')
        poller = ProjectAnnouncements(self.store)
        poller._worker = Mock()
        pending = Future()
        pending.set_result(parse_feed(raw))
        poller._worker.submit.return_value = pending
        with patch('petrel.features.notifications.announcements.datetime') as clock:
            clock.now.return_value = datetime(2027, 1, 1, 11, 59, 59)
            poller.tick()
            poller.tick()
            self.assertEqual(tuple(n.key for n in self.store.snapshot()[1]), ('now',))
            clock.now.return_value = datetime(2027, 1, 1, 12)
            poller.tick()
        poller._worker.submit.assert_called_once()
        self.assertEqual(tuple(n.key for n in self.store.snapshot()[1]), ('new-year', 'now'))

    def test_initial_fetch_after_release_publishes_immediately(self):
        raw = (b'{"version":1,"announcements":['
               b'{"id":"ready","title":"Ready","publish_at":"2027-01-01T12:00:00"}]}')
        poller = ProjectAnnouncements(self.store)
        poller._pending = Future()
        poller._pending.set_result(parse_feed(raw))
        with patch('petrel.features.notifications.announcements.datetime') as clock:
            clock.now.return_value = datetime(2027, 1, 2)
            poller.tick()
        self.assertEqual(tuple(n.key for n in self.store.snapshot()[1]), ('ready',))

    def test_scheduled_ids_do_not_prune_existing_read_markers(self):
        self.store.sync_announcements(feed('same'))
        self.store.dismiss(self.store.snapshot()[1][0])
        self.store.sync_announcements((), scheduled_keys={'same'})
        self.store.sync_announcements(feed('same'))
        self.assertEqual(self.store.snapshot()[1], ())

    def test_invalid_local_schedule_rejects_entire_feed(self):
        for value in ('2027-01-01T12:00Z', '2027-01-01T12:00+03:00',
                      '2027-02-30T12:00', '2027-01-01', None):
            raw = {'version': 1, 'announcements': [
                {'id': 'bad', 'title': 'Bad time', 'publish_at': value},
            ]}
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_feed(json.dumps(raw).encode())

    def test_invalid_or_duplicate_entries_reject_entire_feed(self):
        with self.assertRaises(ValueError):
            feed('first', 'first')
        for raw in (b'{}', b'{"version":1,"announcements":[{"id":"x"}]}'):
            with self.assertRaises(ValueError):
                parse_feed(raw)
