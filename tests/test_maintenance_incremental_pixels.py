"""CI-only pixel equivalence for all incremental Maintenance layouts."""
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch
from PIL import ImageChops
from test_capabilities import display,snapshot
from test_regressions import ui
from test_t5uic1_driver import driver
from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer
from maintenance_experience import Choice,Screen
from maintenance_assessment_store import ServicePolicy
from maintenance_care_view import CareItem
from maintenance_layout import draw_maintenance

class MaintenancePixelUpdates(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.assets=PanelAssets()

    def view(self,screen,selection=0):
        d=display(snapshot());d.lcd=driver();d.fb=Framebuffer(self.assets)
        d.lcd._packet_observer=d.fb;d.lcd.clear(0x2125)
        d._maintenance_init();d._maintenance_page='pulse' if screen.kind=='detail' else 'service' if screen.kind=='care' else 'groups'
        d.pd.maintenance_pulse=NS(display_color=None)
        d._maintenance_selection=selection;draw_maintenance(d,screen)
        return d

    def pixels(self,d):
        d.lcd.update()
        return d.fb.snapshot()[0].crop((0,31,272,360))

    def equal_fresh(self,d,screen):
        fresh=self.view(screen,d._maintenance_selection)
        # A selected row can have several valid retained viewport positions.
        fresh.lcd.draw_rectangle(1,0x2125,0,31,271,359)
        fresh._maintenance_regions={}
        fresh._maintenance_scroll=d._maintenance_scroll
        draw_maintenance(fresh,screen)
        self.assertIsNone(ImageChops.difference(self.pixels(d),self.pixels(fresh)).getbbox())

    def menu(self,count=9,kind='list'):
        return Screen('Cooling',heading='Observe the fan',lines=('Keep hands clear.',),
            choices=(Choice('Back','back'),)+tuple(Choice('Fan '+str(i),'prepare',
                NS(feature_id='F02',device='fan'+str(i)),str(i)+' percent') for i in range(count)),kind=kind)

    @patch('t5uic1_driver.time.sleep')
    @patch.object(ui.time, 'strftime', return_value='12:34')
    def test_header_pixels_match_standard_title_rendering(self,clock,_):
        screen=self.menu(3)
        d=self.view(screen)
        ref=display(snapshot())
        ref.lcd=driver()
        ref.fb=Framebuffer(self.assets)
        ref.lcd._packet_observer=ref.fb
        ref.lcd.clear(0x2125)
        ref.Clear_Title_Bar()
        ref.Draw_Title(screen.title, back=True)
        ref._draw_header_back(True)
        ref.lcd.update()
        d.lcd.update()
        self.assertIsNone(ImageChops.difference(
            d.fb.snapshot()[0].crop((0,0,272,31)),
            ref.fb.snapshot()[0].crop((0,0,272,31))).getbbox())
        # The Maintenance body still starts below the title band.
        self.assertEqual(d.fb.snapshot()[0].getpixel((0,31)),
                         ref.fb.snapshot()[0].getpixel((0,31)))

    @patch('t5uic1_driver.time.sleep')
    def test_list_scroll_forward_back_and_focus_match_fresh(self,_):
        screen=self.menu();d=self.view(screen)
        for selected in (1,5,6,7,8,7,3,1,0):
            d._maintenance_selection=selected;draw_maintenance(d,screen);self.equal_fresh(d,screen)

    @patch('t5uic1_driver.time.sleep')
    def test_action_scroll_and_return_match_fresh(self,_):
        screen=self.menu(7,'detail');d=self.view(screen)
        for selected in (1,3,4,5,4,1,0):
            d._maintenance_selection=selected;draw_maintenance(d,screen);self.equal_fresh(d,screen)

    @patch('t5uic1_driver.time.sleep')
    def test_row_value_and_live_option_count_changes_match_fresh(self,_):
        screen=self.menu(4);d=self.view(screen)
        choices=list(screen.choices);choices[2]=replace(choices[2],detail='Changed value')
        updated=replace(screen,choices=tuple(choices));draw_maintenance(d,updated);self.equal_fresh(d,updated)
        shorter=replace(updated,choices=updated.choices[:3]);draw_maintenance(d,shorter);self.equal_fresh(d,shorter)
        draw_maintenance(d,screen);self.equal_fresh(d,screen)

    @patch('t5uic1_driver.time.sleep')
    def test_care_scroll_and_bar_change_match_fresh(self,_):
        items=tuple(CareItem(ServicePolicy('inspect_clean','fan'+str(i),'calendar_s',100,'user'),
            {'timestamp':1},'not_due','Fan '+str(i),'2 days left',.25,75) for i in range(6))
        screen=Screen('Care schedule',choices=(Choice('Back','back'),)+tuple(Choice(item.label,
            'service_task',(item.policy,item.last,item.state)) for item in items),kind='care',care=items)
        d=self.view(screen)
        for selected in (1,3,4,5,6,5,2,1,0):
            d._maintenance_selection=selected;draw_maintenance(d,screen);self.equal_fresh(d,screen)
        updated=replace(screen,care=(replace(items[0],progress=.5,detail='1 day left'),)+items[1:])
        draw_maintenance(d,updated);self.equal_fresh(d,updated)

if __name__=='__main__': unittest.main()
