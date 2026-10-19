from concurrent.futures import Future
import unittest
from unittest.mock import Mock
from preview_metadata import PreviewData, PreviewDetails, details_from_metadata, amount, duration
from thumbnail_preview import load_preview
from thumbnail_cache import ThumbnailCache
import test_thumbnail_preview as thumbnails
from test_thumbnail_preview import png


def sample():
    return dict(estimated_time=12033,filament_change_count=6,filament_total=7512.75,
                filament_weight_total=22.41,filament_type='["PETG", "PLA", "PLA", "PLA"]',
                filament_colors=['#010101','#FAFEFF','#157BDD','#714302'],
                referenced_tools=[1,2],filament_weights=[0,2.05,20.36,0])


class MetadataTests(unittest.TestCase):
    def test_real_orca_response_uses_tool_indices_not_visible_row_indices(self):
        details=details_from_metadata(sample())
        self.assertEqual(details.seconds,12033)
        self.assertEqual(details.changes,6)
        self.assertEqual([f.tool for f in details.filaments],[1,2])
        self.assertEqual([f.material for f in details.filaments],['PLA','PLA'])
        self.assertEqual([f.grams for f in details.filaments],[2.05,20.36])
        self.assertEqual(details.filaments[1].color,0x13DB)
        self.assertEqual(duration(details.seconds),'3h 20m 33s')
        self.assertEqual(amount(details.millimeters/1000,'m')+'/'+amount(details.grams,'g'),'7.51m/22g')

    def test_all_four_tools_and_plain_single_material(self):
        data=sample();data['referenced_tools']=[3,1,0,2,1];data['filament_type']=['PETG','PLA','ABS','TPU']
        self.assertEqual([f.material for f in details_from_metadata(data).filaments],['PETG','PLA','ABS','TPU'])
        data=dict(filament_type='PLA',filament_colors=['#ffffff'],filament_weights=[4.2])
        f=details_from_metadata(data).filaments[0]
        self.assertEqual((f.tool,f.material,f.grams),(0,'PLA',4.2))

    def test_explicit_unused_tools_are_hidden_and_missing_tools_use_positive_weights(self):
        data=sample();data['referenced_tools']=[]
        self.assertFalse(details_from_metadata(data).filaments)
        del data['referenced_tools']
        self.assertEqual([f.tool for f in details_from_metadata(data).filaments],[1,2])

    def test_missing_or_invalid_values_are_unknown_not_invented(self):
        self.assertEqual(details_from_metadata(None),PreviewDetails())
        data=dict(estimated_time=float('nan'),filament_change_count=True,filament_total=-3,
                  filament_weight_total='22',filament_type=[None],filament_colors=['bad'],
                  filament_weights=[float('inf')],referenced_tools=[True,-1,0,'2',999])
        details=details_from_metadata(data)
        self.assertIsNone(details.seconds);self.assertIsNone(details.changes)
        self.assertIsNone(details.millimeters);self.assertIsNone(details.grams)
        self.assertEqual(details.filaments[0].material,'--')
        self.assertIsNone(details.filaments[0].color);self.assertIsNone(details.filaments[0].grams)
        self.assertEqual(amount(None,'g'),'--g')

    def test_one_metadata_request_supplies_thumbnail_and_details(self):
        client=Mock();data=sample()
        data['thumbnails']=[dict(width=128,height=128,relative_path='.thumbs/a.png')]
        client.get.return_value={'result':data};client.get_bytes.return_value=png()
        preview=load_preview(client,'a.gcode')
        self.assertTrue(preview.jpeg.startswith(b'\xff\xd8'))
        self.assertEqual(preview.details.changes,6)
        client.get.assert_called_once()

    def test_metadata_survives_missing_or_corrupt_thumbnail(self):
        for image in (None,b'invalid'):
            client=Mock();data=sample()
            if image is not None:data['thumbnails']=[dict(width=128,height=128,relative_path='.thumbs/a.png')]
            client.get.return_value={'result':data};client.get_bytes.return_value=image
            preview=load_preview(client,'a.gcode')
            self.assertIsNone(preview.jpeg);self.assertEqual(len(preview.details.filaments),2)

    def test_cache_retains_details_on_hit_and_invalidates_with_file_or_epoch(self):
        key=('a.gcode',1,100,None);future=Future()
        details=details_from_metadata(sample());future.set_result(PreviewData(b'x'*300,details))
        cache=ThumbnailCache(Mock(),loader=Mock(return_value=future));cache.sync(1,[key],[key])
        cache.tick(Mock());cache.tick(Mock(),chunks=8)
        self.assertEqual(cache.details[key],details)
        cache.tick(Mock(),foreground=key);cache.loader.assert_called_once()
        cache.sync(1,[],[]);self.assertFalse(cache.details)
        cache.details[key]=details;cache.sync(2,[key],[key]);self.assertFalse(cache.details)

    def test_missing_thumbnail_details_reach_ui_and_do_not_hide_buttons(self):
        view=thumbnails.ThumbnailTests().make();view.Draw_File_Preview()
        payload_type=view._thumbnail_cache.tick.__func__.__globals__['PreviewData']
        view._preview_future.set_result(payload_type(None,details_from_metadata(sample())))
        view._poll_file_preview()
        texts=[c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertIn('T1',texts);self.assertIn('T2',texts)
        self.assertNotIn('T0',texts);self.assertNotIn('T3',texts)
        self.assertIn('2g',texts);self.assertIn('20g',texts)
        self.assertIn('Print',texts);self.assertIn('Cancel',texts)

    def test_four_rows_fit_and_metadata_is_not_redrawn_on_every_poll(self):
        view=thumbnails.ThumbnailTests().make();data=sample();data['referenced_tools']=[0,1,2,3]
        key=view._preview_cache_key
        view._thumbnail_cache.details[key]=details_from_metadata(data)
        view._thumbnail_cache.entries[key]=(1000,300);view._thumbnail_cache.job=None
        view.Draw_File_Preview();view._poll_file_preview()
        for call in view.lcd.draw_text.call_args_list:
            x,y,text=call.args[-3:]
            self.assertGreaterEqual(x,0);self.assertLessEqual(x+len(text)*8,272)
            self.assertLess(y+16,360)
        texts=[call.args[-1] for call in view.lcd.draw_text.call_args_list]
        for label in ('Print time','Tool changes','Total usage','Filaments used'):
            self.assertIn(label,texts)
        last_row=next(call.args[-2] for call in view.lcd.draw_text.call_args_list if call.args[-1]=='T3')
        button_top=min(call.args[3] for call in view.lcd.draw_rectangle.call_args_list
                       if call.args[2] in (20,146) and call.args[3]>=300)
        self.assertGreaterEqual(button_top-(last_row+16),12)
        view.lcd.reset_mock();view._poll_file_preview()
        view.lcd.draw_text.assert_not_called();view.lcd.write_sram.assert_not_called()
        view.lcd.show_sram_jpeg.assert_not_called()
