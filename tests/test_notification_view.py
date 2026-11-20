import unittest
from unittest.mock import Mock

from petrel.features.notifications.store import Notification, NotificationStore, Retention
from petrel.features.notifications.view import NotificationsViewMixin


class NotificationDisplay(NotificationsViewMixin):
    MainMenu, Info, Prepare, Control, AxisMove, TemperatureID, Motion = range(7)
    ENCODER_DIFF_CW, ENCODER_DIFF_CCW, ENCODER_DIFF_ENTER = range(3)
    ICON = 1
    ICON_Back = 13

    def __init__(self):
        self.checkkey = self.MainMenu
        self.select_page = Mock(now=0)
        self.lcd = Mock()
        self.notifications = NotificationStore()
        self.notification_actions = {}
        self._draw_home_page = Mock()
        self._redraw_current_screen = Mock()
        self._paint_header_title = Mock()

    def send(self, event):
        self.event = event
        return self._notification_input()

    def get_encoder_state(self):
        return self.event


class NotificationViewTest(unittest.TestCase):
    def setUp(self):
        self.view = NotificationDisplay()

    def open_panel(self):
        self.assertTrue(self.view.send(self.view.ENCODER_DIFF_CCW))
        self.assertTrue(self.view.send(self.view.ENCODER_DIFF_ENTER))

    def test_last_dismissal_closes_panel_and_removes_control(self):
        view = self.view
        self.assertFalse(view.send(view.ENCODER_DIFF_CCW))
        self.assertFalse(view._draw_notification_control())
        view.notifications.publish(Notification('test', 'bed', 'Bed cooled down'))
        self.open_panel()
        view.send(view.ENCODER_DIFF_CW)
        view.send(view.ENCODER_DIFF_ENTER)
        self.assertFalse(view._notifications_cover_screen())
        self.assertIsNone(view._notification_focus)
        self.assertIsNone(view._notification_control_render)
        view._redraw_current_screen.assert_called_once()

    def test_persistent_rows_receive_focus_and_scroll_without_drawing_unchanged_rows(self):
        view = self.view
        for index in range(6):
            view.notifications.publish(Notification(
                'test', str(index), f'Reminder {index}', retention=Retention.UNTIL_RESOLVED))
        self.open_panel()
        view._rotation_steps = 6
        view.send(view.ENCODER_DIFF_CW)
        self.assertEqual(view._notification_selection, ('test', '0'))
        self.assertEqual(view._notification_start, 2)
        view.lcd.reset_mock()
        view.send(view.ENCODER_DIFF_ENTER)
        self.assertFalse(view._sync_notification_overlay())
        self.assertEqual(view.lcd.mock_calls, [])
        self.assertEqual(len(view.notifications.snapshot()[1]), 6)

    def test_action_dispatches_and_leaves_persistent_record_until_resolved(self):
        view = self.view
        handler = Mock()
        view.notification_actions['open'] = handler
        item = Notification('test', 'due', 'Maintenance due',
                            retention=Retention.UNTIL_RESOLVED, action='open')
        view.notifications.publish(item)
        self.open_panel()
        view.send(view.ENCODER_DIFF_CW)
        view.send(view.ENCODER_DIFF_ENTER)
        handler.assert_called_once_with(item)
        self.assertEqual(view.notifications.snapshot()[1], (item,))
        self.assertFalse(view._notifications_cover_screen())

    def test_external_resolution_closes_open_panel(self):
        view = self.view
        view.notifications.publish(Notification('test', 'due', 'Maintenance due'))
        self.open_panel()
        view.notifications.resolve('test', 'due')
        self.assertTrue(view._sync_notification_overlay())
        self.assertFalse(view._notifications_cover_screen())
