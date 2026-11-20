import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from petrel.features.notifications.store import (
    ANNOUNCEMENT_SOURCE, Notification, NotificationStore, Persistence, Retention,
)


class NotificationStoreTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'Petrel' / 'notifications.json'

    def test_identity_is_scoped_to_source_and_duplicates_are_noops(self):
        store = NotificationStore()
        print_done = Notification('print', 'done', 'Print completed')
        service_done = Notification('service', 'done', 'Service completed')
        self.assertTrue(store.publish(print_done))
        self.assertFalse(store.publish(print_done))
        self.assertTrue(store.publish(service_done))
        self.assertEqual(store.snapshot(), (2, (service_done, print_done)))

    def test_new_notification_signal_skips_updates_and_restored_entries(self):
        store = NotificationStore(self.path)
        alert = Notification('software', 'update', 'Update available')
        store.publish(alert)
        self.assertTrue(store.take_new_notification_signal())
        self.assertFalse(store.take_new_notification_signal())
        store.publish(alert)
        store.publish(Notification('software', 'update', 'Update available', 'New details'))
        self.assertFalse(store.take_new_notification_signal())

        restarted = NotificationStore(self.path)
        self.assertFalse(restarted.take_new_notification_signal())
        self.assertTrue(restarted.resolve('software', 'update'))
        self.assertFalse(restarted.take_new_notification_signal())
        restarted.publish(alert)
        self.assertTrue(restarted.take_new_notification_signal())

    def test_announcement_signal_only_fires_for_newly_visible_entries(self):
        store = NotificationStore(self.path)
        notice = Notification(ANNOUNCEMENT_SOURCE, 'future', 'Project notice')
        store.sync_announcements([], scheduled_keys={notice.key})
        self.assertFalse(store.take_new_notification_signal())
        store.sync_announcements([notice])
        self.assertTrue(store.take_new_notification_signal())
        store.sync_announcements([notice])
        self.assertFalse(store.take_new_notification_signal())
        self.assertTrue(store.dismiss(notice))
        store.sync_announcements([notice])
        self.assertFalse(store.take_new_notification_signal())

    def test_retention_and_stale_dismissal(self):
        store = NotificationStore()
        original = Notification('print', 'done', 'Print completed')
        updated = Notification('print', 'done', 'Print completed', 'part.gcode')
        reminder = Notification('service', 'belt', 'Maintenance reminder',
                                retention=Retention.UNTIL_RESOLVED, action='service')
        for entry in (original, updated, reminder):
            store.publish(entry)
        self.assertFalse(store.dismiss(original))
        self.assertFalse(store.dismiss(reminder))
        self.assertTrue(store.dismiss(updated))
        self.assertTrue(store.resolve('service', 'belt'))
        self.assertFalse(store.resolve('service', 'belt'))
        self.assertEqual(store.snapshot(), (5, ()))

    def test_restart_restores_only_persistent_entries_and_preserves_order(self):
        store = NotificationStore(self.path)
        alert = Notification('print', 'done', 'Baskı tamamlandı', 'parça.gcode')
        memory_only = Notification('bed', 'cooled', 'Bed cooled',
                                   persistence=Persistence.VOLATILE)
        reminder = Notification('service', 'belt', 'Maintenance due',
                                retention=Retention.UNTIL_RESOLVED, action='open_plan')
        store.publish(memory_only)
        self.assertFalse(self.path.exists())
        store.publish(alert)
        store.publish(reminder)
        self.assertEqual(store.snapshot()[1], (reminder, alert, memory_only))
        restarted = NotificationStore(self.path)
        self.assertEqual(restarted.snapshot()[1], (reminder, alert))
        self.assertFalse(restarted.dismiss(reminder))
        self.assertTrue(restarted.dismiss(alert))
        self.assertEqual(NotificationStore(self.path).snapshot()[1], (reminder,))
        self.assertTrue(restarted.resolve('service', 'belt'))
        self.assertEqual(NotificationStore(self.path).snapshot()[1], ())

    def test_replacing_a_persistent_record_with_a_volatile_one_removes_disk_copy(self):
        store = NotificationStore(self.path)
        store.publish(Notification('print', 'done', 'Persisted'))
        volatile = Notification('print', 'done', 'Temporary', persistence=Persistence.VOLATILE)
        self.assertTrue(store.publish(volatile))
        self.assertEqual(store.snapshot()[1], (volatile,))
        self.assertEqual(NotificationStore(self.path).snapshot()[1], ())

    def test_failed_replace_preserves_previous_disk_and_memory_state(self):
        store = NotificationStore(self.path)
        item = Notification('print', 'done', 'Print done')
        store.publish(item)
        with patch('petrel.features.notifications.store.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                store.dismiss(item)
        self.assertEqual(store.snapshot(), (1, (item,)))
        self.assertEqual(NotificationStore(self.path).snapshot()[1], (item,))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_state_is_preserved_and_volatile_notifications_still_work(self):
        self.path.parent.mkdir()
        self.path.write_text('{"version":99}', encoding='utf-8')
        with self.assertLogs(level='WARNING'):
            store = NotificationStore(self.path)
        store.publish(Notification('bed', 'cooled', 'Bed cooled', persistence=Persistence.VOLATILE))
        with self.assertRaises(OSError):
            store.publish(Notification('print', 'done', 'Print done'))
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{"version":99}')
        self.assertEqual(len(store.snapshot()[1]), 1)
