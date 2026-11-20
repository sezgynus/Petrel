import unittest
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from petrel.features.maintenance.assessment.store import ServicePolicy
from petrel.features.maintenance.notification import ACTION, SOURCE, reconcile_care_notifications
from petrel.features.notifications.store import Notification, NotificationStore
from test_capabilities import display, snapshot


class MaintenanceNotificationTests(unittest.TestCase):
    def test_due_cycle_survives_restart_and_unknown_counter_until_service_is_recorded(self):
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / 'notifications.json'
        store = NotificationStore(path)
        store.publish(Notification('other', 'notice', 'Another notification'))
        fan = ServicePolicy('fan', 'fan', 'sampled_on_s', 10, 'user')
        belt = ServicePolicy('mechanical', 'stepper_x', 'calendar_s', 10, 'user')
        first = {'timestamp': 100.0}
        plans = ((fan, first, 'due'), (belt, first, 'due'))
        due_state = lambda policy, last, cached: cached
        reconcile_care_notifications(store, plans, due_state)
        self.assertEqual(len(store.snapshot()[1]), 3)
        self.assertTrue(all(not store.dismiss(item) for item in store.snapshot()[1]
                            if item.source == SOURCE))

        store = NotificationStore(path)
        reconcile_care_notifications(store, ((fan, first, 'unknown'), plans[1]), due_state)
        self.assertEqual(store.snapshot()[0], 0)
        self.assertEqual(len(store.snapshot()[1]), 3)
        reconcile_care_notifications(store, ((fan, {'timestamp': 120.0}, 'unknown'), plans[1]), due_state)
        self.assertEqual(len(store.snapshot()[1]), 2)
        self.assertEqual(len(NotificationStore(path).snapshot()[1]), 2)
        self.assertTrue(any(item.source == 'other' for item in store.snapshot()[1]))

    def test_background_load_publishes_calendar_due_and_action_opens_the_exact_plan(self):
        view = display(snapshot())
        view.checkkey = view.MainMenu
        view.notifications = NotificationStore()
        view.notification_actions = {ACTION: view._open_maintenance_notification}
        fan = ServicePolicy('fan', 'fan', 'calendar_s', 10, 'user')
        other = ServicePolicy('heating', 'heater_bed', 'calendar_s', 10, 'user')
        pending = Future()
        view.pd.maintenance_ui_records = Mock(return_value=pending)
        view.Draw_Maintenance_Menu = Mock()
        with patch.dict(view._maintenance_policy_due.__globals__, {'time': lambda: 120.0}):
            view._poll_maintenance_ui()
            view.pd.maintenance_ui_records.assert_called_once_with('load', policy=None, history=False)
            pending.set_result((((other, {'timestamp': 119.0}, 'not_due'),
                                 (fan, {'timestamp': 105.0}, 'not_due')), ()))
            view._poll_maintenance_ui()
            view.Draw_Maintenance_Menu.assert_not_called()
            items = view.notifications.snapshot()[1]
            self.assertEqual(len(items), 1)
            view._notification_overlay = view.MainMenu
            view._activate_notification(items, 0)
        self.assertEqual(view.checkkey, view.MaintenanceMenu)
        self.assertEqual(view._maintenance_page, 'service_task')
        self.assertEqual(view._maintenance_context[0], fan)
        self.assertEqual(view.notifications.snapshot()[1], items)

        completed = Future()
        view.pd.maintenance_ui_records.return_value = completed
        view._maintenance_load_records('complete', fan)
        self.assertEqual(view.notifications.snapshot()[1], items)
        completed.set_result((((fan, {'timestamp': 120.0}, 'not_due'),), ()))
        with patch.dict(view._maintenance_policy_due.__globals__, {'time': lambda: 120.0}):
            view._poll_maintenance_ui()
        self.assertEqual(view.notifications.snapshot()[1], ())
