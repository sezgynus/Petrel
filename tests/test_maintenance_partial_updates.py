"""CI coverage of every shared Maintenance layout/update path."""
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock
from test_capabilities import display,snapshot
from maintenance_experience import Choice,Screen
from maintenance_care_view import CareItem
from maintenance_assessment_store import ServicePolicy
from maintenance_layout import draw_maintenance,_bar,BG,LINE

class MaintenancePartialUpdates(unittest.TestCase):
    def view(self,page='groups'):
        d=display(snapshot());d.checkkey=d.MaintenanceMenu;d._maintenance_init()
        d._maintenance_page=page
        d.pd.maintenance_pulse=NS(phase=None,pending=False,available=lambda:())
        return d

    def menu(self,count=8,kind='list'):
        return Screen('Checks',choices=(Choice('Back','back'),)+tuple(
            Choice('Check '+str(i),'prepare',NS(feature_id='F02',device='fan'), 'Reading '+str(i)) for i in range(1,count+1)),kind=kind)

    def no_full_clear(self,d):
        for c in d.lcd.draw_rectangle.call_args_list:
            x,y,x1,y1=c.args[-4:]
            self.assertFalse(x<=16 and x1>=258 and y<90 and y1>=330,c)
            self.assertLess(y1,360)

    def test_focus_only_is_cursor_only_for_list_and_detail(self):
        for kind in ('list','detail'):
            with self.subTest(kind=kind):
                d=self.view();screen=self.menu(3,kind)
                d._maintenance_selection=1
                draw_maintenance(d,screen);d.lcd.reset_mock()
                d._maintenance_selection=2;draw_maintenance(d,screen)
                d.lcd.draw_text.assert_not_called();d.lcd.show_icon.assert_not_called()
                d.lcd.move_area.assert_not_called();self.no_full_clear(d)
                self.assertTrue(all(c.args[-4]==4 and c.args[-2]==7 for c in d.lcd.draw_rectangle.call_args_list))

    def test_list_scroll_moves_pixels_and_draws_only_the_exposed_row(self):
        d=self.view();screen=self.menu()
        d._maintenance_selection=1
        draw_maintenance(d,screen);d.lcd.reset_mock()
        d._maintenance_selection=7;draw_maintenance(d,screen)
        d.lcd.move_area.assert_called_once_with(1,d.DWIN_SCROLL_UP,52,BG,0,34,259,345)
        self.assertEqual(d.lcd.show_icon.call_count,1)
        strings=[c.args[-1] for c in d.lcd.draw_text.call_args_list]
        self.assertIn('Check 7',strings);self.assertNotIn('Check 2',strings)
        self.no_full_clear(d)
        d.lcd.reset_mock();d._maintenance_selection=1;draw_maintenance(d,screen)
        d.lcd.move_area.assert_called_once_with(1,d.DWIN_SCROLL_DOWN,52,BG,0,34,259,345)
        self.assertEqual(d.lcd.show_icon.call_count,1)

    def test_one_row_value_update_keeps_label_and_icon(self):
        d=self.view();screen=self.menu(3)
        draw_maintenance(d,screen);d.lcd.reset_mock()
        choices=list(screen.choices);choices[2]=replace(choices[2],detail='Reading changed')
        draw_maintenance(d,replace(screen,choices=tuple(choices)))
        d.lcd.show_icon.assert_not_called();d.lcd.move_area.assert_not_called()
        self.assertEqual([c.args[-1] for c in d.lcd.draw_text.call_args_list],['Reading changed'])
        self.assertTrue(all(c.args[-4]==60 and c.args[-3]==114 for c in d.lcd.draw_rectangle.call_args_list))

    def test_care_scroll_reuses_two_existing_rows(self):
        d=self.view('service')
        items=tuple(CareItem(ServicePolicy('inspect_clean','fan'+str(i),'calendar_s',100,'user'),
            {'timestamp':1},'not_due','Fan '+str(i),'1d left',.25,75) for i in range(5))
        screen=Screen('Care schedule',choices=(Choice('Back','back'),)+tuple(
            Choice(item.label,'service_task',(item.policy,item.last,item.state)) for item in items),kind='care',care=items)
        d._maintenance_selection=1
        draw_maintenance(d,screen);d.lcd.reset_mock()
        d._maintenance_selection=5;draw_maintenance(d,screen)
        d.lcd.move_area.assert_called_once_with(1,d.DWIN_SCROLL_UP,80,BG,0,34,259,353)
        strings=[c.args[-1] for c in d.lcd.draw_text.call_args_list]
        self.assertIn('Fan 4',strings);self.assertNotIn('Fan 1',strings)
        self.no_full_clear(d)

    def test_bar_growth_changes_only_new_pixels_and_reset_removes_old_fill(self):
        d=self.view();item=NS(progress=.25,state='not_due')
        _bar(d,'test',item,24,150,200);d.lcd.reset_mock()
        _bar(d,'test',NS(progress=.30,state='not_due'),24,150,200)
        self.assertEqual(d.lcd.draw_rectangle.call_count,1)
        self.assertEqual(d.lcd.draw_rectangle.call_args.args[-4:],(74,150,83,153))
        d.lcd.reset_mock();_bar(d,'test',NS(progress=0,state='unknown'),24,150,200)
        self.assertEqual(d.lcd.draw_rectangle.call_args.args[-4:],(24,150,83,153))

    def test_action_scroll_keeps_heading_and_instruction_pixels(self):
        d=self.view('pulse');screen=self.menu(7,'detail')
        draw_maintenance(d,screen);d.lcd.reset_mock()
        d._maintenance_selection=4;draw_maintenance(d,screen)
        d.lcd.move_area.assert_called_once_with(1,d.DWIN_SCROLL_UP,39,BG,0,241,259,357)
        self.assertTrue(all(c.args[-3]>=220 or (c.args[-4]==4 and c.args[-2] in (7,27))
                            for c in d.lcd.draw_rectangle.call_args_list))
        self.no_full_clear(d)

    def test_choice_count_change_does_not_clear_the_frame(self):
        d=self.view();screen=self.menu(3)
        draw_maintenance(d,screen);d.lcd.reset_mock()
        draw_maintenance(d,self.menu(4))
        self.no_full_clear(d)
        d.lcd.reset_mock();draw_maintenance(d,self.menu(2))
        self.no_full_clear(d)

    def test_encoder_focus_reuses_drawn_model_but_enter_revalidates(self):
        d=self.view();screen=self.menu(3)
        d._maintenance_screen=Mock(return_value=screen)
        d.Draw_Maintenance_Menu();d._maintenance_screen.reset_mock()
        d.get_encoder_state=Mock(return_value=d.ENCODER_DIFF_CW)
        d.HMI_Maintenance_Menu();d._maintenance_screen.assert_not_called()
        d.get_encoder_state.return_value=d.ENCODER_DIFF_ENTER
        d._maintenance_dispatch=Mock()
        d.HMI_Maintenance_Menu();d._maintenance_screen.assert_called_once_with()

if __name__=='__main__': unittest.main()
