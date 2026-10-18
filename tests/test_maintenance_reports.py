"""CI-only report hierarchy, paging and incremental framebuffer regressions."""
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
from maintenance_report import ReportSection,report_pages,section_from_lines
from maintenance_layout import draw_maintenance

class MaintenanceReports(unittest.TestCase):
    def view(self,pixels=False):
        d=display(snapshot());d._maintenance_init();d._maintenance_page='details'
        if pixels:
            d.lcd=driver();d.fb=Framebuffer(PanelAssets());d.lcd._packet_observer=d.fb;d.lcd.clear(0x2125)
        return d

    def screen(self):
        return Screen('Diagnostic data','Host load and memory',choices=(Choice('Back','back'),
            Choice('Next page','report_page',1),Choice('Previous page','report_page',0),
            Choice('Details','details'),Choice('Check printer','open','groups')),kind='report',badge='INFORMATION',
            sections=(ReportSection('Host',facts=tuple(('Reading '+str(i),str(i)+' %') for i in range(13))),))

    def test_report_facts_are_not_fake_menu_choices(self):
        d=self.view();d._maintenance_page='result'
        d._maintenance_result=NS(feature_id='S01',status=None,evidence=(('cpu.cpu',36.5),('memory.available',193992)))
        screen=d._maintenance_screen()
        self.assertEqual(screen.kind,'report')
        self.assertTrue(all(c.action!='none' for c in screen.choices))
        self.assertIn('36.5 %',str(screen.sections))
        self.assertNotIn('36.5',str(screen.choices))

    def test_all_facts_and_guidance_survive_bounded_pagination(self):
        sections=section_from_lines('Measurements',tuple('Reading %d: %d mm'%(i,i) for i in range(40)))
        pages=report_pages(sections)
        self.assertGreater(len(pages),1)
        self.assertTrue(all(sum(b[2] for b in p)<=132 for p in pages))
        labels=[cell[0][0] for p in pages for kind,content,h in p if kind=='facts' for cell in content]
        self.assertEqual(labels,['Reading '+str(i) for i in range(40)])
        prose=report_pages((ReportSection(text=('Keep hands clear. '*80,)),))
        self.assertTrue(all(sum(b[2] for b in p)<=132 for p in prose))
        self.assertEqual(sum(b[1][0].count('clear.') for p in prose for b in p),80)

    def test_focus_and_unchanged_refresh_only_touch_action_cursors(self):
        d=self.view();screen=self.screen();draw_maintenance(d,screen);d.lcd.reset_mock()
        draw_maintenance(d,screen)
        d.lcd.draw_text.assert_not_called();d.lcd.draw_rectangle.assert_not_called()
        d._maintenance_selection=1;draw_maintenance(d,screen)
        d.lcd.draw_text.assert_not_called();d.lcd.show_icon.assert_not_called()
        self.assertTrue(all(c.args[-4]==4 and c.args[-2]==7 for c in d.lcd.draw_rectangle.call_args_list))

    def test_one_measurement_update_only_redraws_its_value(self):
        d=self.view();screen=self.screen();draw_maintenance(d,screen);d.lcd.reset_mock()
        section=screen.sections[0];facts=list(section.facts);facts[0]=(facts[0][0],'75 %')
        draw_maintenance(d,replace(screen,sections=(replace(section,facts=tuple(facts)),)))
        self.assertEqual([c.args[-1] for c in d.lcd.draw_text.call_args_list],['75 %'])
        d.lcd.show_icon.assert_not_called()
        self.assertEqual(d.lcd.draw_rectangle.call_count,1)

    def test_paging_is_explicit_and_never_observes_or_starts_hardware(self):
        d=self.view();d._maintenance_page='instructions';d._maintenance_context=('Read safely. '*90,)
        d.pd.observe_maintenance_physical=Mock();d.pd.start_maintenance_physical=Mock()
        first=d._maintenance_screen()
        next_page=next(c for c in first.choices if c.action=='report_page')
        d._maintenance_dispatch(next_page)
        self.assertEqual(d._maintenance_screen().report_page,1)
        self.assertTrue(any(c.label=='Previous page' for c in d._maintenance_screen().choices))
        d.pd.observe_maintenance_physical.assert_not_called();d.pd.start_maintenance_physical.assert_not_called()

    @patch('t5uic1_driver.time.sleep')
    def test_report_pages_focus_and_action_scroll_match_clean_pixels(self,_):
        d=self.view(True);screen=self.screen()
        def compare():
            fresh=self.view(True);fresh._maintenance_selection=d._maintenance_selection
            draw_maintenance(fresh,screen)
            fresh.lcd.draw_rectangle(1,0x2125,0,31,271,359);fresh._maintenance_regions={}
            fresh._maintenance_scroll=d._maintenance_scroll;draw_maintenance(fresh,screen)
            d.lcd.update();fresh.lcd.update()
            self.assertIsNone(ImageChops.difference(d.fb.snapshot()[0],fresh.fb.snapshot()[0]).getbbox())
        draw_maintenance(d,screen);compare()
        for selected in (1,2,3,4,2,0):
            d._maintenance_selection=selected;draw_maintenance(d,screen);compare()
        for page in (1,2,0):
            screen=replace(screen,report_page=page);draw_maintenance(d,screen);compare()
        section=screen.sections[0]
        screen=replace(screen,sections=(replace(section,facts=(('Reading 0','80 %'),)+section.facts[1:]),))
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
