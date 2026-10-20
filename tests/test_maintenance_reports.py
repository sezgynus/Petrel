"""CI-only continuous report scrolling, bounded redraw and pixel equivalence."""
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from PIL import ImageChops
from test_capabilities import display,snapshot
from test_t5uic1_driver import driver
from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer
from maintenance_experience import Choice,Screen
from maintenance_report import (ReportSection,report_rows,section_from_lines,
    report_navigation,REPORT_VISIBLE_ROWS,REPORT_TOP,REPORT_ROW_HEIGHT)
from maintenance_layout import draw_maintenance,BG

class MaintenanceReports(unittest.TestCase):
    def view(self,pixels=False):
        d=display(snapshot());d._maintenance_init();d._maintenance_page='details'
        if pixels:
            d.lcd=driver();d.fb=Framebuffer(PanelAssets());d.lcd._packet_observer=d.fb;d.lcd.clear(BG)
        return d

    def screen(self,count=13):
        return Screen('Diagnostic data','Host load and memory',choices=(Choice('Back','back'),
            Choice('Details','details'),Choice('Check printer','open','groups')),kind='report',badge='INFORMATION',
            sections=(ReportSection('Host',facts=tuple(('Reading '+str(i),str(i)+' %') for i in range(count))),))

    def test_report_facts_are_not_fake_menu_choices(self):
        d=self.view();d._maintenance_page='result'
        d._maintenance_result=NS(feature_id='S01',status=None,evidence=(('cpu.cpu',36.5),('memory.available',193992)))
        screen=d._maintenance_screen()
        self.assertEqual(screen.kind,'report')
        self.assertTrue(all(c.action not in ('none','report_page') for c in screen.choices))
        self.assertIn('36.5 %',str(screen.sections))
        self.assertNotIn('36.5',str(screen.choices))

    def test_all_facts_long_labels_values_and_guidance_survive_rows(self):
        sections=section_from_lines('Measurements',tuple('Reading %d: %d mm'%(i,i) for i in range(128)))
        rows=report_rows(sections)
        labels=[line for row in rows for cell in row.cells if cell.role=='label' for line in cell.lines]
        self.assertEqual(labels,['Reading '+str(i) for i in range(128)])
        prose=report_rows((ReportSection(text=('Keep hands clear. '*80,)),))
        self.assertEqual(sum(line.count('clear.') for row in prose for c in row.cells for line in c.lines),80)
        rows=report_rows((ReportSection(facts=(('Long label '*20,'long value '*40),)),))
        self.assertEqual(sum(line.count('label') for r in rows for c in r.cells for line in c.lines),20)
        self.assertEqual(sum(line.count('value') for r in rows for c in r.cells for line in c.lines),40)
        self.assertTrue(all(len(c.lines)<=2 and (c.small or len(c.lines)==1) for r in rows for c in r.cells))

    def test_focus_and_unchanged_refresh_only_touch_action_cursors(self):
        d=self.view();screen=self.screen()
        maximum=max(0,len(report_rows(screen.sections,screen.choices))-REPORT_VISIBLE_ROWS)
        screen=replace(screen,report_offset=maximum)
        draw_maintenance(d,screen);d.lcd.reset_mock();draw_maintenance(d,screen)
        d.lcd.draw_text.assert_not_called();d.lcd.draw_rectangle.assert_not_called()
        d._maintenance_selection=1;draw_maintenance(d,screen)
        d.lcd.draw_text.assert_not_called();d.lcd.show_icon.assert_not_called()
        self.assertTrue(all(c.args[-4]==4 and c.args[-2]==7 for c in d.lcd.draw_rectangle.call_args_list))

    def test_one_measurement_update_only_redraws_its_value(self):
        d=self.view();screen=self.screen();draw_maintenance(d,screen);d.lcd.reset_mock()
        section=screen.sections[0];facts=list(section.facts);facts[0]=(facts[0][0],'75 %')
        draw_maintenance(d,replace(screen,sections=(replace(section,facts=tuple(facts)),)))
        self.assertEqual([c.args[-1] for c in d.lcd.draw_text.call_args_list],['75 %'])
        d.lcd.show_icon.assert_not_called();self.assertEqual(d.lcd.draw_rectangle.call_count,1)

    def test_scrolling_moves_one_band_and_only_draws_exposed_cells(self):
        d=self.view();screen=self.screen();draw_maintenance(d,screen);d.lcd.reset_mock()
        draw_maintenance(d,replace(screen,report_offset=1))
        d.lcd.move_area.assert_called_once_with(1,d.DWIN_SCROLL_UP,24,BG,0,148,259,339)
        self.assertLessEqual(d.lcd.draw_text.call_count,2)
        d.lcd.show_icon.assert_not_called()
        for call in d.lcd.draw_rectangle.call_args_list:
            x,y,x1,y1=call.args[-4:]
            self.assertLess(y1,360)
            self.assertFalse(x<=16 and x1>=258 and y<148 and y1>=339)
        d.lcd.reset_mock();draw_maintenance(d,screen)
        d.lcd.move_area.assert_called_once_with(1,d.DWIN_SCROLL_DOWN,24,BG,0,148,259,339)
        self.assertEqual([c.args[-1] for c in d.lcd.draw_text.call_args_list],['Host'])

    def test_encoder_scroll_wraps_both_directions_without_actuation_or_reflow(self):
        d=self.view();d._maintenance_page='instructions';d._maintenance_context=('Read safely. '*90,)
        d.pd.observe_maintenance_physical=Mock();d.pd.start_maintenance_physical=Mock()
        d.Draw_Maintenance_Menu()
        screen=d._maintenance_last_screen
        self.assertFalse(any(c.action=='report_page' for c in screen.choices))
        rows=report_rows(screen.sections,screen.choices)
        count=report_navigation(rows,screen.choices,0)[3]
        d.get_encoder_state=Mock(return_value=d.ENCODER_DIFF_CW)
        with patch('maintenance_report.report_rows',side_effect=AssertionError('encoder reflow')):
            d._menu_batch_steps=count-1;d.HMI_Maintenance_Menu()
            self.assertEqual(d._maintenance_report_position,count-1)
            d._menu_batch_steps=1;d.HMI_Maintenance_Menu()
            self.assertEqual(d._maintenance_report_position,0)
            self.assertEqual(d._maintenance_last_screen.report_offset,0)
            d.get_encoder_state.return_value=d.ENCODER_DIFF_CCW;d.HMI_Maintenance_Menu()
            self.assertEqual(d._maintenance_report_position,count-1)
        d.pd.observe_maintenance_physical.assert_not_called();d.pd.start_maintenance_physical.assert_not_called()

    def test_each_action_is_visible_when_focused_even_with_long_action_list(self):
        choices=(Choice('Back','back'),)+tuple(Choice('Action '+str(i),'details') for i in range(14))
        rows=report_rows((ReportSection(text=('Explanation. '*50,)),),choices)
        maximum=max(0,len(rows)-REPORT_VISIBLE_ROWS)
        for selected in range(1,len(choices)):
            position,offset,index,count=report_navigation(rows,choices,maximum+selected)
            self.assertEqual(index,selected)
            self.assertTrue(any(r.choice==selected for r in rows[offset:offset+REPORT_VISIBLE_ROWS]))
        self.assertEqual(report_navigation(rows,choices,count)[0],0)

    @patch('t5uic1_driver.time.sleep')
    def test_incremental_scroll_wrap_focus_and_updates_match_clean_pixels(self,_):
        d=self.view(True);screen=self.screen(25)
        def compare():
            fresh=self.view(True);fresh._maintenance_selection=d._maintenance_selection
            draw_maintenance(fresh,screen)
            d.lcd.update();fresh.lcd.update()
            self.assertIsNone(ImageChops.difference(d.fb.snapshot()[0],fresh.fb.snapshot()[0]).getbbox())
        maximum=len(report_rows(screen.sections,screen.choices))-REPORT_VISIBLE_ROWS
        draw_maintenance(d,screen);compare()
        for offset in (1,2,5,4,1,0,maximum,0,maximum):
            screen=replace(screen,report_offset=offset);draw_maintenance(d,screen);compare()
        for selected in (1,2,1,0):
            d._maintenance_selection=selected;draw_maintenance(d,screen);compare()
        section=screen.sections[0]
        screen=replace(screen,sections=(replace(section,facts=section.facts[:-1]+(('Changed label','80 %'),)),))
        draw_maintenance(d,screen);compare()
        screen=replace(screen,sections=(ReportSection(text=('Short report.',)),),report_offset=0)
        draw_maintenance(d,screen);compare()

    def test_documentation_care_records_have_real_mixed_progress(self):
        from tools import render_docs_screenshots as renderer
        from tools.maintenance_doc_scenes import register
        captures=[]
        def observe(v):
            captures.append(v._maintenance_last_screen)
            return None
        scenes=[]
        def scene(*metadata):
            return lambda draw:scenes.append((metadata[0],draw))
        register(scene,renderer.canvas,observe)
        next(draw for name,draw in scenes if name=='maintenance')()
        screen=captures[-1]
        self.assertEqual(screen.heading,'5 plans / 0 due')
        self.assertEqual(len(screen.care),2)
        self.assertTrue(all(0<item.progress<1 and item.remaining>0 for item in screen.care))

    def test_host_units_are_readable_and_cpu_names_are_unambiguous(self):
        from maintenance_evidence_view import evidence_lines
        lines=evidence_lines('S01',(('memory.available',193992),('cpu.cpu0',42.1)))
        self.assertIn('Memory available: 189.4 MiB',lines)
        self.assertIn('Core 0: 42.1 %',lines)
