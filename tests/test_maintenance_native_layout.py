"""CI-only regressions for the approved fixed Maintenance hierarchy."""
import unittest
from concurrent.futures import Future
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from test_capabilities import display, snapshot
from maintenance_assessment_store import ServicePolicy
from maintenance_care_view import care_items
from maintenance_experience import Choice


class CarePresentation(unittest.TestCase):
    def policy(self,device='fan',basis='calendar_s',interval=100):
        return ServicePolicy('inspect_clean',device,basis,interval,'user')

    def test_five_policies_are_prioritized_without_inventing_dates(self):
        rows=tuple((self.policy(str(i)),{'timestamp':stamp},'not_due')
                   for i,stamp in enumerate((0,20,60,80,95)))
        items=care_items(rows,{str(i) for i in range(5)},120)
        self.assertEqual(len(items),5)
        self.assertEqual([x.state for x in items[:2]],['due','due'])
        self.assertEqual(items[0].progress,1)
        self.assertAlmostEqual(items[-1].progress,.25)
        self.assertLess(items[0].remaining,items[1].remaining)

    def test_unknown_or_future_service_never_has_a_filled_bar(self):
        p=self.policy()
        for last in (None,{'timestamp':200}):
            item=care_items(((p,last,'due'),),{'fan'},100)[0]
            self.assertEqual(item.state,'unknown')
            self.assertIsNone(item.progress)
            self.assertIsNone(item.remaining)

    def test_recorded_fraction_is_visible_without_claiming_remaining_life(self):
        p=self.policy(basis='sampled_on_s',interval=20*3600)
        item=care_items(((p,{'_sampled_elapsed_s':8*3600},'unknown'),),{'fan'},100)[0]
        self.assertAlmostEqual(item.progress,.4)
        self.assertEqual(item.detail,'8/20h recorded')
        self.assertIsNone(item.remaining)
        self.assertEqual(item.state,'unknown')

    def test_removed_device_does_not_appear(self):
        self.assertEqual(care_items(((self.policy(),None,'due'),),{'other'},100),())

    def test_sampled_time_never_claims_known_remaining_life(self):
        p=self.policy(basis='sampled_on_s')
        item=care_items(((p,{'timestamp':1},'unknown'),),{'fan'},100)[0]
        self.assertIsNone(item.progress)
        self.assertIsNone(item.remaining)
        due=care_items(((p,{'timestamp':1},'due'),),{'fan'},100)[0]
        self.assertEqual(due.progress,1)
        self.assertIsNone(due.remaining)


class NativeMaintenanceLayout(unittest.TestCase):
    def view(self):
        d=display(snapshot());d.checkkey=d.MaintenanceMenu;d._maintenance_init()
        d.pd.maintenance_pulse=NS(phase=None,pending=False,available=lambda:())
        d.get_encoder_state=Mock(return_value=d.ENCODER_DIFF_ENTER)
        return d

    def set_plans(self,d,count=5):
        devices=[NS(name='fan'+str(i)) for i in range(count)]
        real=d._maintenance_identity()
        d.pd.maintenance=NS(snapshot=NS(epoch=real[0],config_marker=real[1],devices=devices))
        d._maintenance_records_ready=True
        d._maintenance_records_identity=d._maintenance_identity()
        d._maintenance_records_data=(tuple((ServicePolicy('inspect_clean',x.name,'calendar_s',100,'user'),
            {'timestamp':i*10},'not_due') for i,x in enumerate(devices)),())
        d._maintenance_options=Mock(return_value=(tuple(NS(device=x.name) for x in devices),()))
        d.pd.maintenance_assessment_details=Mock(return_value=NS(findings=(),trends=()))
        d.pd.maintenance_assessment.has_current_evidence=Mock(return_value=True)

    def test_root_stays_five_choices_with_five_plans_and_many_recommendations(self):
        d=self.view();self.set_plans(d)
        findings=tuple(NS(device='fan',state='attention') for _ in range(11))
        d.pd.maintenance_assessment_details.return_value=NS(findings=findings,trends=())
        with patch('ui_maintenance.time',return_value=120):
            screen=d._maintenance_screen()
        self.assertEqual([c.label for c in screen.choices],
            ['Back','Care schedule','Check printer','Diagnostics','Recommendations (11)'])
        self.assertEqual(len(screen.care),2)
        self.assertIn('5 plans',screen.heading)

    def test_title_bar_uses_standard_header_and_preserves_body_boundary(self):
        d=self.view()
        d.Draw_Maintenance_Menu()
        rectangles=[call.args for call in d.lcd.draw_rectangle.call_args_list]
        self.assertEqual(rectangles[0],
                         (1,d.lcd.Color_Bg_Blue,0,0,271,30))
        self.assertIn((1,0x2125,0,31,271,359),rectangles)
        self.assertNotIn((1,0x2125,0,0,271,359),rectangles)
        d.lcd.draw_text.assert_any_call(
            False,False,d.lcd.font8x16,d.lcd.Color_White,
            d.lcd.Color_Bg_Blue,34,6,'Maintenance')
        d.lcd.reset_mock()
        d._maintenance_selection=2
        d.Draw_Maintenance_Menu()
        self.assertFalse(any(
            call.args[2:]==(0,0,271,30)
            for call in d.lcd.draw_rectangle.call_args_list))
        self.assertFalse(any(
            call.args[5:7]==(14,6)
            for call in d.lcd.draw_text.call_args_list))

    def test_focus_changes_only_cursor_strips_and_preserves_dashboard(self):
        d=self.view();d._maintenance_selection=2;d.Draw_Maintenance_Menu();d.lcd.reset_mock()
        d._maintenance_selection=3;d.Draw_Maintenance_Menu()
        d.lcd.draw_text.assert_not_called();d.lcd.show_icon.assert_not_called()
        for call in d.lcd.draw_rectangle.call_args_list:
            self.assertEqual(call.args[-4],4)
            self.assertEqual(call.args[-2],7)
            self.assertLess(call.args[-1],360)

    def test_care_list_scrolls_all_five_policies_and_preserves_drawn_action(self):
        d=self.view();self.set_plans(d);d._maintenance_page='service'
        with patch('ui_maintenance.time',return_value=120):
            d.Draw_Maintenance_Menu()
            screen=d._maintenance_screen()
            self.assertEqual(sum(c.action=='service_task' for c in screen.choices),5)
            d._maintenance_selection=5;d.Draw_Maintenance_Menu()
            self.assertGreater(d._maintenance_scroll,0)
            action=d._maintenance_drawn_choices[5]
            self.assertEqual(action[0],'service_task')
            self.assertEqual(action[1][0].device,'fan4')
        for call in d.lcd.draw_rectangle.call_args_list:
            self.assertLessEqual(call.args[-1],359)

    def test_background_record_load_does_not_take_over_another_screen(self):
        d=self.view();f=Future();d.pd.maintenance_ui_records=Mock(return_value=f)
        d.Enter_Maintenance_Menu()
        self.assertEqual(d._maintenance_page,'root')
        context=object();d._maintenance_context=context;d._maintenance_page='prepare'
        f.set_result(((),()))
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page,'prepare')
        self.assertIs(d._maintenance_context,context)
        self.assertTrue(d._maintenance_records_ready)

    def test_background_failure_neither_changes_context_nor_claims_saved_plans(self):
        d=self.view();f=Future();d.pd.maintenance_ui_records=Mock(return_value=f)
        d.Enter_Maintenance_Menu();d._maintenance_page='service_interval'
        context=('fan','inspect_clean',30);d._maintenance_context=context
        f.set_exception(OSError('disk error'));d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page,'service_interval')
        self.assertEqual(d._maintenance_context,context)
        self.assertTrue(d._maintenance_records_failed)
        self.assertFalse(d._maintenance_records_ready)

    def test_diagnostics_is_a_root_destination_with_history_and_support(self):
        d=self.view();screen=d._maintenance_screen()
        c=next(c for c in screen.choices if c.label=='Diagnostics')
        d._maintenance_dispatch(c)
        screen=d._maintenance_screen()
        self.assertEqual(screen.title,'Diagnostics')
        self.assertTrue(any(c.action=='history' for c in screen.choices))
        self.assertTrue(any(c.value=='support' for c in screen.choices))


if __name__=='__main__':
    unittest.main()
