"""CI-only Mainsail-default print timing and metadata lifecycle contracts."""
import time
import unittest
from concurrent.futures import Future
from unittest.mock import Mock
from print_estimates import progress, estimates, finish_text
from test_capabilities import printer, snapshot
import test_print_focus


class PrintEstimateTests(unittest.TestCase):
    def test_relative_file_progress_excludes_metadata_bytes_and_clamps(self):
        metadata = {'gcode_start_byte': 100, 'gcode_end_byte': 1100}
        self.assertEqual(progress({'file_position': 400, 'progress': .4}, metadata), .3)
        self.assertEqual(progress({'file_position': 50}, metadata), 0)
        self.assertEqual(progress({'file_position': 1200}, metadata), 1)
        self.assertEqual(progress({'progress': .4}, {}), .4)
        self.assertEqual(progress({'file_position': 400, 'progress': .4},
                                  {'gcode_start_byte': 100, 'gcode_end_byte': 50}), .4)

    def test_remaining_and_eta_use_distinct_mainsail_default_source_sets(self):
        stats = {'state': 'printing', 'print_duration': 600, 'total_duration': 900,
                 'filament_used': 200}
        metadata = {'filament_total': 1000, 'estimated_time': 3600}
        # File: 5400 s, filament: 2400 s; slicer: 3000 s.
        self.assertEqual(estimates(stats, {'progress': .1}, metadata), (3900, 3600))
        self.assertEqual(estimates(stats, {'progress': .1}, {}), (5400, 5400))
        self.assertEqual(estimates(stats, {'progress': 0}, {'estimated_time': 3600}), (None, 3000))

    def test_invalid_missing_and_overdue_sources_never_invent_a_finish(self):
        for stats, sd, metadata in (
            ({'state':'printing','print_duration':0},{'progress':.5},{}),
            ({'state':'printing','print_duration':600},{'progress':1},{'estimated_time':500}),
            ({'state':'printing','print_duration':float('nan')},{'progress':float('inf')},{}),
            ({'state':'printing','print_duration':True},{'progress':.1},{})):
            self.assertEqual(estimates(stats, sd, metadata), (None, None))
        for state in ('standby','complete','cancelled','error'):
            self.assertEqual(estimates({'state':state,'print_duration':600}, {'progress':.1}, {}), (None,None))
        self.assertEqual(finish_text(0, None), 'Finish --:--')

    def test_finish_labels_calendar_day_difference(self):
        now = time.mktime((2026,10,18,23,30,0,0,0,-1))
        self.assertEqual(finish_text(now, 600), 'Finish 23:40')
        self.assertEqual(finish_text(now, 7200), 'Finish 01:30 +1')
        self.assertEqual(finish_text(now, 26*3600), 'Finish 01:30 +2')

    def test_total_elapsed_preserves_print_only_fallback_and_terminal_stats(self):
        p = printer(snapshot())
        p.job_Info = {key: dict(value) for key, value in p.job_Info.items()}
        for state in ('printing','paused','complete','cancelled','error'):
            p.job_Info['print_stats'].update(state=state,print_duration=600,total_duration=900)
            self.assertEqual(p.duration(),900)
        del p.job_Info['print_stats']['total_duration']
        self.assertEqual(p.duration(),600)
        p.job_Info['print_stats']['state']='standby'
        self.assertEqual(p.duration(),0)

    def test_metadata_is_async_cached_bounded_and_invalidated_by_file_identity(self):
        p = printer(snapshot())
        p.job_Info = {key: dict(value) for key, value in p.job_Info.items()}
        p.job_Info['print_stats'].update(state='printing',filename='folder/a b.gcode')
        first, second = Future(), Future()
        p._read_worker = Mock()
        p._read_worker.submit.side_effect = [first, second]
        p.getREST = Mock(return_value={'result':{}})
        p._refresh_print_metadata()
        p._refresh_print_metadata()
        self.assertEqual(p._read_worker.submit.call_count,1)
        work=p._read_worker.submit.call_args.args[0]
        work()
        p.getREST.assert_called_once_with('/server/files/metadata?filename=folder%2Fa%20b.gcode')
        first.set_result({'result':{'estimated_time':3600,'filament_total':1000,
                                    'gcode_start_byte':100,'gcode_end_byte':1100,
                                    'large_unneeded_data':'ignored'}})
        p._refresh_print_metadata()
        p._refresh_print_metadata()
        self.assertEqual(p._read_worker.submit.call_count,1)
        self.assertEqual(len(p._current_print_metadata()),4)
        p.job_Info['virtual_sdcard'].update(progress=.4,file_position=400)
        self.assertEqual(p.getPercent(),30)
        p.job_Info['print_stats']['filename']='other.gcode'
        self.assertEqual(p._current_print_metadata(),{})
        p._refresh_print_metadata()
        self.assertEqual(p._read_worker.submit.call_count,2)
        self.assertEqual(p._current_print_metadata(),{})

    def test_print_screen_displays_total_elapsed_separate_eta_and_unknown_values(self):
        v,_=test_print_focus.PrintFocusTests().view()
        v.pd.job_Info = {key: dict(value) for key, value in v.pd.job_Info.items()}
        v.pd.job_Info['print_stats'].update(print_duration=600,total_duration=900,filament_used=200)
        v.pd.job_Info['virtual_sdcard']['progress']=.1
        v.pd._print_metadata_stamp=(v.pd.state.epoch,v.pd.state.file_revision,'part.gcode')
        v.pd._print_metadata={'filament_total':1000,'estimated_time':3600}
        v._focus_print_tick()
        self.assertEqual(v._focus_render['elapsed'],'00:15')
        self.assertEqual(v._focus_render['remain'],'01:05')
        v.pd.job_Info['print_stats']['print_duration']=0
        v._focus_print_tick()
        self.assertEqual(v._focus_render['remain'],'--:--')
        self.assertEqual(v._focus_render['finish'],'Finish --:--')
