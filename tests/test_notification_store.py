import unittest

from petrel.features.notifications.store import Notification, NotificationStore, Retention


class NotificationStoreTest(unittest.TestCase):
    def test_identity_is_scoped_to_source_and_duplicates_are_noops(self):
        store = NotificationStore()
        print_done = Notification('print', 'done', 'Print completed')
        service_done = Notification('service', 'done', 'Service completed')
        self.assertTrue(store.publish(print_done))
        self.assertFalse(store.publish(print_done))
        self.assertTrue(store.publish(service_done))
        self.assertEqual(store.snapshot(), (2, (service_done, print_done)))

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
