"""Safety contracts for externally started prints and idle-only LCD commands."""
import unittest
from unittest.mock import Mock

from operation_guards import idle_dispatch_guard
from test_capabilities import snapshot, display, printer


class ExternalPrintSafetyTests(unittest.TestCase):
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
