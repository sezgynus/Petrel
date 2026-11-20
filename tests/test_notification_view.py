import unittest
from types import SimpleNamespace
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

    def test_submenus_share_visibility_and_encoder_order(self):
        for name, position in NotificationDisplay._notification_positions.items():
            with self.subTest(menu=name):
                view = NotificationDisplay()
                view.pd = SimpleNamespace()
                if not hasattr(view, name):
                    setattr(view, name, 100)
                view.checkkey = getattr(view, name)
                view._draw_notification_focus_change = Mock()
                if name == 'PrintErrorDetails':
                    view._focus_error_choice = 1
                if position is not None:
                    setattr(view, position, 0)
                view.notifications.publish(Notification('test', 'due', 'Maintenance due'))
                self.assertTrue(view._draw_notification_control())
                follows_back = view._notification_follows_back()
                into_bell = view.ENCODER_DIFF_CW if follows_back else view.ENCODER_DIFF_CCW
                back = view.ENCODER_DIFF_CCW if follows_back else view.ENCODER_DIFF_CW
                self.assertTrue(view.send(into_bell))
                self.assertEqual(view._notification_focus, view.checkkey)
                self.assertTrue(view.send(back))
                self.assertIsNone(view._notification_focus)
                self.assertTrue(view.send(into_bell))
                self.assertTrue(view.send(view.ENCODER_DIFF_ENTER))
                self.assertTrue(view._notifications_cover_screen())

    def test_bell_is_between_back_and_the_first_menu_item_in_both_directions(self):
        view = self.view
        view.checkkey = view.Prepare
        view.select_prepare = SimpleNamespace(now=0)
        view._header_back_render = (id(view.lcd), True)
        view._draw_header_back = Mock()
        view.notifications.publish(Notification('test', 'due', 'Maintenance due'))

        self.assertFalse(view.send(view.ENCODER_DIFF_CCW))
        self.assertTrue(view.send(view.ENCODER_DIFF_CW))
        self.assertEqual(view._notification_focus, view.Prepare)
        self.assertFalse(view.send(view.ENCODER_DIFF_CW))
        self.assertIsNone(view._notification_focus)

        view.select_prepare.now = 1
        view.event = view.ENCODER_DIFF_CCW
        previous = view._notification_menu_position()
        view.select_prepare.now = 0
        view._notification_return_from_menu(previous)
        self.assertEqual(view._notification_focus, view.Prepare)
        self.assertTrue(view.send(view.ENCODER_DIFF_CCW))
        self.assertIsNone(view._notification_focus)

    def test_display_edit_owns_encoder_and_hides_notification_control(self):
        view = self.view
        view.DisplayMenu = view.checkkey = 100
        view._display_edit = True
        view.notifications.publish(Notification('test', 'due', 'Maintenance due'))
        self.assertFalse(view._draw_notification_control())
        self.assertFalse(view.send(view.ENCODER_DIFF_CCW))
        view._display_edit = False
        self.assertTrue(view._draw_notification_control())
        self.assertTrue(view.send(view.ENCODER_DIFF_CCW))

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
