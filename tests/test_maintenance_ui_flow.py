"""End-user Maintenance navigation, explicit consent and evidence provenance."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from test_capabilities import display,snapshot
from maintenance_experience import Choice

class MaintenanceUIFlows(unittest.TestCase):
    def view(self):
        d=display(snapshot())
        d.checkkey=d.MaintenanceMenu
        d._maintenance_init()
        d.pd.maintenance_pulse=NS(phase=None,pending=False,available=lambda:())
        d.get_encoder_state=Mock(return_value=d.ENCODER_DIFF_ENTER)
        d.pd.client.get.reset_mock()
        return d

    def owner(self,d,phase,feature='F01',**kw):
        data=dict(phase=phase,pending=True,feature_id=feature,live_text=())
        data.update(kw)
        d.pd.maintenance_pulse=NS(**data)
        d._maintenance_page='pulse'
        return d.pd.maintenance_pulse

    def choose(self,d,action,value=None):
        d.Draw_Maintenance_Menu()
        screen=d._maintenance_screen()
        index=next(i for i,c in enumerate(screen.choices) if c.action==action and (value is None or c.value==value))
        d._maintenance_selection=index
        d.HMI_Maintenance_Menu()

    def test_root_has_purpose_tiles_and_no_io(self):
        d=self.view();d.Draw_Maintenance_Menu()
        self.assertEqual([c.label for c in d._maintenance_screen().choices],
            ['Back','Check printer','Findings','Service plan','More'])
        d.pd.client.get.assert_not_called()

    def test_capability_checks_require_preparation_and_second_confirmation(self):
        d=self.view()
        row=NS(feature_id='F01',device='fan',method=2,visible=True)
        d.pd.maintenance_guided_plan=Mock(return_value=(row,))
        d.pd.start_maintenance_physical=Mock(return_value=(True,'queued'))
        d.pd.confirm_maintenance_physical=Mock(return_value=(True,'queued'))
        d._maintenance_dispatch(Choice('Checks','open','groups'))
        self.choose(d,'targets');self.choose(d,'prepare')
        d.pd.start_maintenance_physical.assert_not_called()
        self.choose(d,'start')
        d.pd.start_maintenance_physical.assert_called_once_with('F01','fan')
        self.owner(d,'await_confirmation')
        d.Draw_Maintenance_Menu()
        d.pd.confirm_maintenance_physical.assert_not_called()
        self.choose(d,'confirm')
        d.pd.confirm_maintenance_physical.assert_called_once_with()

    def test_empty_groups_do_not_invent_checks(self):
        d=self.view();d.pd.maintenance_guided_plan=Mock(return_value=())
        d._maintenance_page='groups'
        self.assertEqual(len(d._maintenance_screen().choices),1)

    def test_result_back_restores_same_device_and_selection(self):
        d=self.view();row=NS(feature_id='F01',device='fan',method=2)
        d._maintenance_page='prepare';d._maintenance_context=row;d._maintenance_selection=1
        d.pd.start_maintenance_physical=Mock(return_value=(False,'not_safe'))
        self.choose(d,'start');self.assertEqual(d._maintenance_page,'result')
        self.choose(d,'result_back')
        self.assertEqual(d._maintenance_page,'prepare')
        self.assertIs(d._maintenance_context,row)
        self.assertEqual(d._maintenance_selection,1)

    def test_nested_back_restores_parent_without_start(self):
        d=self.view();d._maintenance_selection=4
        d._maintenance_open('more');d._maintenance_open('diagnostics')
        d._maintenance_back();self.assertEqual(d._maintenance_page,'more')
        d._maintenance_back();self.assertEqual(d._maintenance_selection,4)

    def test_observation_positive_and_negative_are_explicit(self):
        for seen in (False,True):
            d=self.view();self.owner(d,'await_observation',observation_prompt='Did it rotate?')
            d.pd.observe_maintenance_physical=Mock(return_value=NS(status='PASSED_USER'))
            self.choose(d,'observe',seen)
            d.pd.observe_maintenance_physical.assert_called_once_with(seen)
            self.assertEqual(d._maintenance_page,'result')

    def test_observation_details_do_not_accept_without_review_choice(self):
        d=self.view();self.owner(d,'await_observation','M12',observation_details=('Trigger phase: 7/64',))
        d.pd.observe_maintenance_physical=Mock(return_value=NS(status='OBSERVED_USER'))
        self.choose(d,'review');self.assertEqual(d._maintenance_page,'details')
        d.pd.observe_maintenance_physical.assert_not_called()
        d._maintenance_back();self.choose(d,'observe',True)
        d.pd.observe_maintenance_physical.assert_called_once_with(True)

    def test_fan_steps_and_stop_transition_redraw_immediately(self):
        d=self.view();owner=self.owner(d,'await_observation','F12',pwm_levels=(0,32,64,96,127))
        def observe(n): owner.phase='f12_await_stop'
        d.pd.observe_maintenance_physical=Mock(side_effect=observe)
        self.choose(d,'observe',3)
        self.assertEqual(d._maintenance_screen().title,'Fan startup')
        self.assertTrue(any(c.action=='fan_stop' for c in d._maintenance_screen().choices))
        d.pd.observe_maintenance_physical.assert_called_once_with(3)

    def test_fan_stop_can_start_next_round(self):
        d=self.view();self.owner(d,'f12_await_stop','F12')
        d.pd.confirm_maintenance_f12_stopped=Mock(return_value=(True,'queued'))
        self.choose(d,'fan_stop');self.assertEqual(d._maintenance_page,'pulse')

    def test_fan_stop_rejected_round_shows_blocked_reason(self):
        d=self.view();self.owner(d,'f12_await_stop','F12')
        d.pd.confirm_maintenance_f12_stopped=Mock(return_value=(False,'maintenance_busy'))
        self.choose(d,'fan_stop')
        self.assertEqual(d._maintenance_page,'result')
        self.assertEqual(d._maintenance_result.status,'BLOCKED')
        self.assertEqual(d._maintenance_result.reason,'maintenance_busy')
        self.assertEqual(d._maintenance_screen().heading,'Preparation required')

    def test_pending_cancellation_never_manufactures_completion(self):
        d=self.view();self.owner(d,'running','H01')
        d.pd.cancel_maintenance_physical=Mock(return_value=None)
        self.choose(d,'cancel');self.assertEqual(d._maintenance_page,'pulse')
        self.assertEqual(d._maintenance_screen().choices[0].label,'Stop: Klipper shutdown')

    def test_completed_cancel_has_result(self):
        d=self.view();self.owner(d,'await_confirmation')
        d.pd.cancel_maintenance_physical=Mock(return_value=NS(status='ABORTED'))
        self.choose(d,'cancel');self.assertEqual(d._maintenance_page,'result')

    def test_measurement_editor_uses_actual_value_and_encoder_steps(self):
        d=self.view();owner=self.owner(d,'measurement_edit','M06',measurement_value=10.,measurement_unit='mm')
        owner.adjust_measurement=Mock(side_effect=lambda x:setattr(owner,'measurement_value',owner.measurement_value+x))
        owner.record_measurement=Mock(return_value=(True,'queued'))
        d._menu_batch_steps=2;d.get_encoder_state.return_value=d.ENCODER_DIFF_CW
        d.HMI_Maintenance_Menu();self.assertAlmostEqual(owner.measurement_value,10.02)
        d.get_encoder_state.return_value=d.ENCODER_DIFF_ENTER
        self.choose(d,'record');owner.record_measurement.assert_called_once_with(10.02)

    def test_workflow_choices_preserve_controller_index(self):
        d=self.view();owner=self.owner(d,'workflow','P01',workflow_choices=(('Read released','a'),('Read triggered','b')))
        owner.choose=Mock(return_value=(True,'queued'))
        self.choose(d,'choose',1);owner.choose.assert_called_once_with(1)

    def test_homing_is_announced_before_any_motion(self):
        d=self.view();self.owner(d,'await_confirmation','M04',preparing_home=True)
        screen=d._maintenance_screen()
        self.assertEqual(screen.heading,'Clear the homing path')
        self.assertIn('Home axes and continue',[c.label for c in screen.choices])

    def test_controller_poll_keeps_offscreen_operation_alive(self):
        d=self.view();self.owner(d,'running');d.checkkey=d.MainMenu
        d.pd.poll_maintenance_physical=Mock(return_value=None)
        d._poll_maintenance_ui();d.pd.poll_maintenance_physical.assert_called_once_with()

    def test_background_result_updates_visible_view(self):
        d=self.view();self.owner(d,'running')
        d.pd.poll_maintenance_physical=Mock(return_value=NS(status='INCONCLUSIVE',reason='restore_not_verified'))
        d._poll_maintenance_ui();self.assertEqual(d._maintenance_page,'result')
        self.assertEqual(d._maintenance_result.status,'INCONCLUSIVE')

    def test_information_read_is_explicit_and_preserves_target(self):
        d=self.view();row=NS(feature_id='M07',device='tmc2208 stepper_x')
        d.pd.maintenance_read_plan=Mock(return_value=(row,))
        d.pd.start_maintenance_read=Mock(return_value=(True,'queued'))
        d._maintenance_page='diagnostics';d.Draw_Maintenance_Menu()
        d.pd.start_maintenance_read.assert_not_called()
        self.choose(d,'read')
        d.pd.start_maintenance_read.assert_called_once_with('M07',device='tmc2208 stepper_x')

    def test_raw_numeric_evidence_is_only_in_optional_details(self):
        d=self.view();d._maintenance_page='result'
        d._maintenance_result=NS(feature_id='H01',status='PASSED_USER',reason='',evidence=(('overshoot_c',7.72),))
        screen=d._maintenance_screen()
        self.assertNotIn('7.72',str((screen.heading,screen.lines)))
        self.choose(d,'details');self.assertIn('7.72',str(d._maintenance_screen()))

    def test_shaper_is_klipper_suggestion_and_never_saved_implicitly(self):
        d=self.view();d._maintenance_page='result'
        d._maintenance_result=NS(feature_id='R04',status='OBSERVED',reason='',evidence=(('shaper','mzv'),('frequency_hz',34.6),('saved',False)))
        screen=d._maintenance_screen()
        self.assertEqual(screen.heading,'Klipper tuning suggestion')
        self.assertIn('Not saved to printer.cfg.',screen.lines)
        self.choose(d,'details');self.assertIn('34.6',str(d._maintenance_screen()))

    def test_repeated_draw_sends_no_unchanged_packets(self):
        d=self.view();d.Draw_Maintenance_Menu();d.lcd.reset_mock()
        d.Draw_Maintenance_Menu()
        d.lcd.draw_rectangle.assert_not_called()
        d.lcd.draw_text.assert_not_called()
        d.lcd.show_icon.assert_not_called()

    def test_recording_is_in_support_and_never_starts_check(self):
        d=self.view();d._maintenance_page='support'
        d.pd.toggle_maintenance_test_recording=Mock()
        d.pd.start_maintenance_physical=Mock()
        self.choose(d,'trace')
        d.pd.toggle_maintenance_test_recording.assert_called_once_with()
        d.pd.start_maintenance_physical.assert_not_called()

    def test_declined_observation_is_not_changed_by_passive_poll(self):
        d=self.view();self.owner(d,'await_observation')
        d.pd.poll_maintenance_physical=Mock(return_value=None)
        d.pd.observe_maintenance_physical=Mock()
        for _ in range(3): d._poll_maintenance_ui()
        d.pd.observe_maintenance_physical.assert_not_called()

    def test_managed_tile_ids_skip_the_reserved_qr_slot(self):
        import lcd_resources as icons
        self.assertEqual(icons.ICON_MAINTENANCE_CHECK,156)
        self.assertEqual(icons.ICON_MAINTENANCE_MORE_SELECTED,163)
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        self.assertFalse((root/'assets/icons/155.jpg').exists())
        for index in range(156,164):
            self.assertTrue((root/('assets/icons/%d.jpg'%index)).exists())

