"""Safety contracts for externally started prints and idle-only LCD commands."""
import unittest
from unittest.mock import Mock

from operation_guards import idle_dispatch_guard
from test_capabilities import snapshot, display, printer


class ExternalPrintSafetyTests(unittest.TestCase):
    def test_external_start_drops_stale_idle_operation_feedback(self):
        v = display(snapshot())
        v.checkkey = v.Control
        v._action_feedback = Mock()
        v._action_on_accept = Mock()
        v._pending_start = ('stale', 1, 0)
        v._start_error_visible = True
        v.pd.last_command_error = 'Old control command rejected'
        v.pd.status = 'printing'
        v.Goto_PrintProcess = Mock(side_effect=lambda: setattr(v, 'checkkey', v.PrintProcess))
        v._present_print_state()
        self.assertEqual(v.checkkey, v.PrintProcess)
        self.assertIsNone(v._action_feedback)
        self.assertIsNone(v._action_on_accept)
        self.assertIsNone(v._pending_start)
        self.assertFalse(v._start_error_visible)
        self.assertIsNone(v.pd.last_command_error)

    def test_print_start_guard_is_revoked_by_external_job(self):
        p = printer(snapshot())
        p._files_loaded = True
        p.file_error = False
        p.files = [{'path': 'a.gcode'}]
        p.postREST = Mock()
        p.openAndPrintFile('a.gcode')
        guard = p.postREST.call_args.kwargs['dispatch_guard']
        self.assertTrue(guard())
        source = p.subscription.snapshot.return_value
        source['status']['print_stats']['state'] = 'printing'
        self.assertFalse(guard())

    def test_tune_dispatch_guard_rejects_job_change_after_submission(self):
        source = snapshot()
        source['status']['print_stats'].update(
            state='printing', filename='part.gcode', print_duration=30, total_duration=30)
        source['print_job_generation'] = 5
        p = printer(source)
        token = p.print_job_identity()
        p.set_print_setting('speed', 125, expected_job=token)
        guard = p.sendGCode.call_args.kwargs['dispatch_guard']
        self.assertTrue(guard())
        source['print_job_generation'] = 6
        self.assertFalse(guard())
        p.sendGCode.reset_mock()
        with self.assertRaises(ValueError):
            p.set_print_setting('speed', 125, expected_job=token)
        p.sendGCode.assert_not_called()

    def test_job_identity_changes_and_stale_cancel_is_rejected(self):
        from concurrent.futures import Future
        source = snapshot()
        source['status']['print_stats'].update(
            state='printing', filename='old.gcode', print_duration=100, total_duration=100)
        source['print_job_generation'] = 7
        p = printer(source)
        p.subscription.request.return_value = Future()
        old = p.print_job_identity()
        self.assertTrue(p.print_job_matches(old))
        source['status']['print_stats'].update(
            filename='new.gcode', print_duration=0, total_duration=0)
        source['print_job_generation'] = 8
        self.assertFalse(p.print_job_matches(old))
        returned = p.cancel_job(expected_job=old)
        self.assertTrue(returned.done())
        self.assertIsInstance(returned.exception(), ValueError)
        p.subscription.request.assert_not_called()

    def test_print_origin_mmu_rejects_new_job_generation(self):
        source = snapshot()
        source['status']['print_stats'].update(
            state='printing', filename='part.gcode', print_duration=90)
        source['print_job_generation'] = 3
        v = display(source)
        v.checkkey = v.PrintProcess
        v.Enter_MMU_Menu()
        self.assertFalse(v._active_print_requires_focus())
        source['print_job_generation'] = 4
        v.pd.status = 'printing'
        self.assertTrue(v._active_print_requires_focus())

    def test_stale_idle_dispatch_refused(self):
        for change in ('printing', 'paused', 'pausing', 'active_sd', 'pause_resume', 'epoch', 'disconnected'):
            source = snapshot()
            p = printer(source)
            guard = idle_dispatch_guard(p)
            self.assertTrue(guard())
            if change in ('printing', 'paused', 'pausing'):
                source['status']['print_stats']['state'] = change
            elif change == 'active_sd':
                source['status']['virtual_sdcard']['is_active'] = True
            elif change == 'pause_resume':
                source['status']['pause_resume'] = {'is_paused': True}
            elif change == 'epoch':
                source['epoch'] += 1
            else:
                source['state'] = 'disconnected'
            with self.subTest(change=change):
                self.assertFalse(guard())

    def test_idle_only_commands_reject_active_print(self):
        operations = (
            lambda p: p.cooldown(idle_only=True),
            lambda p: p.preHeat(60, 200, idle_only=True),
            lambda p: p.set_motion_limit('max_velocity', 80, idle_only=True),
            lambda p: p.setZOffset(.1, idle_only=True),
            lambda p: p.setBedTemp(60, idle_only=True),
            lambda p: p.setExtTemp(200, idle_only=True),
            lambda p: p.setFanSpeed(30, idle_only=True),
        )
        for action in operations:
            source = snapshot()
            p = printer(source)
            source['status']['print_stats']['state'] = 'printing'
            with self.subTest(action=action), self.assertRaises(ValueError):
                action(p)
            p.sendGCode.assert_not_called()

    def test_dispatch_guard_revoked_if_job_starts_after_enqueue(self):
        source = snapshot()
        p = printer(source)
        p.cooldown(idle_only=True)
        guard = p.sendGCode.call_args.kwargs['dispatch_guard']
        self.assertTrue(guard())
        source['status']['print_stats']['state'] = 'printing'
        self.assertFalse(guard())

    def test_old_idle_mmu_cannot_suppress_active_print(self):
        v = display(snapshot())
        v.checkkey = v.MMUMenu
        v._mmu_return_print = False
        v.pd.status = 'printing'
        v.last_status = 'printing'  # Previous MMU loop consumed the edge.
        v.Goto_PrintProcess = Mock(side_effect=lambda: setattr(v, 'checkkey', v.PrintProcess))
        self.assertTrue(v._active_print_requires_focus())
        v._present_print_state()
        self.assertEqual(v.checkkey, v.PrintProcess)

    def test_stale_menu_focus_and_intentional_print_mmu(self):
        v = display(snapshot())
        v.pd.status = 'printing'
        for screen in (v.MainMenu, v.Prepare, v.Control, v.AxisMove,
                       v.MotionValue, v.TemperatureID, v.MMUMenu):
            v.checkkey = screen
            v._mmu_return_print = False
            with self.subTest(screen=screen):
                self.assertTrue(v._active_print_requires_focus())
        v._mmu_return_print = True
        v.checkkey = v.MMUMenu
        self.assertFalse(v._active_print_requires_focus())
        for screen in (v.PrintProcess, v.Tune, v.TuneEdit, v.PrintErrorDetails, v.Print_window):
            v.checkkey = screen
            self.assertFalse(v._active_print_requires_focus())


if __name__ == '__main__':
    unittest.main()
