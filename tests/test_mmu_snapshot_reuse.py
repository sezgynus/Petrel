"""Render-local reuse must never become stale display or command authority."""
from unittest.mock import patch
import unittest

import test_mmu_ui as ui
from test_mmu_control import add_led_status, hardware_status


class MMUSnapshotReuseTests(unittest.TestCase):
    def make(self):
        view, data = ui.MMUUITests().make()
        data['status']['mmu_machine'] = hardware_status()
        add_led_status(data)
        return view, data

    def test_each_menu_draw_takes_one_snapshot_for_all_rows(self):
        for page in ('home', 'more', 'gates', 'gate', 'bypass', 'maintenance',
                     'options', 'leds', 'recover', 'map', 'endless', 'spool'):
            with self.subTest(page=page):
                view, _ = self.make()
                view._mmu_open(page)  # Initialize any edit draft before measurement.
                view.pd.subscription.snapshot.reset_mock()
                view.Draw_MMU_Menu()
                view.pd.subscription.snapshot.assert_called_once_with()
                view.pd.subscription.request.assert_not_called()

    def test_next_draw_reads_changed_live_mapping(self):
        view, data = self.make()
        view.Draw_MMU_Menu()
        self.assertIn(('tool', 0, data['status']['mmu']['ttg_map'][0]), view._mmu_drawn_keys)
        data['status']['mmu']['ttg_map'][0] = 3
        view.Draw_MMU_Menu()
        self.assertIn(('tool', 0, 3), view._mmu_drawn_keys)

    def test_next_draw_locks_actions_when_print_starts(self):
        view, data = self.make()
        data['status']['print_stats']['state'] = 'printing'
        view.Draw_MMU_Menu()
        items = view._mmu_items(view.pd.mmu_session.state)
        self.assertTrue(all(not item[3] for item in items if item[0][0] in ('tool', 'action')))
        view.pd.subscription.request.assert_not_called()

    def test_dispatch_rechecks_changes_after_menu_eligibility(self):
        view, data = self.make()
        build = view._mmu_items
        def change_after_build(*args, **kwargs):
            items = build(*args, **kwargs)
            data['status']['print_stats']['state'] = 'printing'
            return items
        view._mmu_selection = 2  # T1, not the already selected T0.
        view.get_encoder_state.return_value = view.ENCODER_DIFF_ENTER
        with patch.object(view, '_mmu_items', side_effect=change_after_build):
            view.HMI_MMU_Menu()
        view.pd.subscription.request.assert_not_called()
        self.assertIn('Printing', view._mmu_notice)


if __name__ == '__main__':
    unittest.main()
