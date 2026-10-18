import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from test_capabilities import display,snapshot
from maintenance_assessment_model import Finding

class MaintenanceUISafety(unittest.TestCase):
    def view(self):
        d=display(snapshot());d.checkkey=d.MaintenanceMenu;d._maintenance_init()
        d.get_encoder_state=Mock(return_value=d.ENCODER_DIFF_ENTER)
        d.pd.maintenance_pulse=NS(phase='await_confirmation',pending=True,feature_id='F01',live_text=(),available=lambda:())
        return d

    def test_stale_enter_is_not_an_observation_or_command(self):
        d=self.view();d._maintenance_page='pulse';d._maintenance_selection=1
        d.Draw_Maintenance_Menu()
        d.pd.maintenance_pulse.phase='await_observation'
        d.pd.observe_maintenance_physical=Mock();d.pd.confirm_maintenance_physical=Mock()
        d.HMI_Maintenance_Menu()
        d.pd.observe_maintenance_physical.assert_not_called()
        d.pd.confirm_maintenance_physical.assert_not_called()
        self.assertEqual(d._maintenance_selection,0)

    def test_phase_change_resets_focus_to_nonpositive_action(self):
        d=self.view();d._maintenance_page='pulse';d._maintenance_selection=1
        def poll():d.pd.maintenance_pulse.phase='await_observation'
        d.pd.poll_maintenance_physical=Mock(side_effect=poll)
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_selection,0)
        self.assertFalse(d._maintenance_screen().choices[0].value)

    def test_long_workflow_instructions_are_reachable_without_confirmation(self):
        d=self.view();d._maintenance_page='pulse'
        d.pd.maintenance_pulse.live_text=tuple('Line '+str(i)+' with complete instruction' for i in range(12))
        screen=d._maintenance_screen()
        choice=next(c for c in screen.choices if c.action=='instructions')
        d.pd.confirm_maintenance_physical=Mock()
        d._maintenance_dispatch(choice)
        self.assertEqual(d._maintenance_page,'instructions')
        self.assertIn('11',str(d._maintenance_screen()))
        d.pd.confirm_maintenance_physical.assert_not_called()

    def test_multiple_findings_are_grouped_by_device_not_test_code(self):
        d=self.view();d._maintenance_page='findings'
        findings=(Finding('check.H07','extruder','attention','thermal.overshoot_review'),
                  Finding('check.H08','extruder','attention','thermal.stability_review'))
        d.pd.maintenance_assessment_details=Mock(return_value=NS(findings=findings,trends=()))
        choices=d._maintenance_screen().choices
        self.assertEqual(len(choices),2)
        self.assertEqual(choices[1].label,'Hotend')
        self.assertEqual(len(choices[1].value),2)

    def test_renderer_keeps_content_above_the_status_strip(self):
        d=self.view();d._maintenance_page='pulse';d.Draw_Maintenance_Menu()
        for call in d.lcd.draw_rectangle.call_args_list:
            self.assertLessEqual(call.args[-1],359)
        d.lcd.reset_mock();d.Draw_Maintenance_Menu()
        d.lcd.draw_rectangle.assert_not_called()

    def test_cancelled_power_overlay_repaints_maintenance_without_restarting_check(self):
        d=self.view();d._maintenance_page='root';d.Draw_Maintenance_Menu()
        d._power_origin=d.MaintenanceMenu
        d._restore_power_editor=Mock(return_value=False)
        d.pd.start_maintenance_physical=Mock()
        d.lcd.reset_mock()
        d._restore_power_origin()
        d.lcd.show_icon.assert_called()
        d.pd.start_maintenance_physical.assert_not_called()
        self.assertEqual(d.checkkey,d.MaintenanceMenu)

    def test_external_measurement_preparation_mentions_instrument(self):
        from maintenance_experience import preparation
        row=NS(feature_id='M06',method=4)
        self.assertIn('ruler',' '.join(preparation(row)))
        self.assertIn('travel path',' '.join(preparation(row)))

    def test_home_counts_devices_with_findings_without_claiming_global_health(self):
        d=self.view();d._maintenance_page='root'
        findings=(Finding('check.H07','extruder','attention','thermal.overshoot_review'),
                  Finding('check.H08','extruder','attention','thermal.stability_review'))
        d.pd.maintenance_assessment.has_current_evidence=Mock(return_value=True)
        d.pd.maintenance_assessment_details=Mock(return_value=NS(findings=findings,trends=()))
        self.assertEqual(d._maintenance_screen().choices[4].label,'Recommendations (2)')
        self.assertEqual(len(d._maintenance_screen().choices),5)
        d.pd.maintenance_assessment_details.return_value=NS(findings=(),trends=())
        self.assertEqual(d._maintenance_screen().heading,'Load saved care plans')

    def test_empty_evidence_home_never_builds_a_report_or_plan(self):
        d=self.view();d._maintenance_page='root'
        d.pd.maintenance_assessment_details=Mock(side_effect=AssertionError('unexpected planning'))
        d.pd.maintenance=NS(snapshot=NS(epoch=1,config_marker=123))
        self.assertEqual(d._maintenance_screen().heading,'Load saved care plans')
        d.pd.maintenance_assessment_details.assert_not_called()
