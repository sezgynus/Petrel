"""CI-only data preparation and active-file invalidation contracts."""
from concurrent.futures import Future
from unittest.mock import Mock
from threading import current_thread
from dataclasses import replace
import unittest
from petrel.moonraker.subscription import MoonrakerSubscription
from petrel.printer.background_reads import ReadWorker, ReadPending
from test_capabilities import printer, snapshot, display
from petrel.ui.events import InputEvent
from petrel.features.buzzer.control import Player

class AuditHotpathTests(unittest.TestCase):
    def test_input_and_read_stamp_do_not_copy_full_config(self):
        v=display(snapshot());v._closed=False;v._uart_online=True;v._loop=Mock()
        v._action_feedback=None
        v.pd.subscription.lifecycle.return_value={'state':'ready','epoch':1}
        v.pd.subscription.snapshot.side_effect=AssertionError('full copy')
        self.assertTrue(v._enqueue_input('rotate',1))
        self.assertEqual(v.pd._read('small',lambda:'ok'),'ok')

    def test_buzzer_never_copies_moonraker_configuration(self):
        from petrel.features.buzzer.control import Settings
        s=MoonrakerSubscription('http://localhost:7125',autostart=False)
        s.snapshot=Mock(side_effect=AssertionError('full copy'))
        s.notify_immediate=Mock(side_effect=AssertionError('Klipper buzzer'))
        pwm=Mock()
        p=Player(s, driver_factory=lambda: pwm)
        try:
            self.assertTrue(p.play(Settings(), 'press'))
            p.cancel()
        finally:
            p.close()
            s.close()
        s.snapshot.assert_not_called()
        s.notify_immediate.assert_not_called()

    def test_file_validation_sort_and_index_are_prepared_on_worker(self):
        p=printer(snapshot());worker=ReadWorker(timeout=.1);p._read_worker=worker
        self.addCleanup(worker.close)
        owner=current_thread();seen=[]
        original=p._sort_files
        def sort(*a,**k):seen.append(current_thread());return original(*a,**k)
        p._sort_files=sort
        p._file_sort_refresh_at=float('inf')
        p.getREST=Mock(return_value={'result':[{'path':'b.gcode'},{'path':'a.gcode'}]})
        p.GetFiles()
        pending=p._read_jobs['files'][1];pending.result(1)
        paths=p.GetFiles()
        self.assertEqual(paths,('a.gcode','b.gcode'))
        self.assertTrue(seen);self.assertTrue(all(t is not owner for t in seen))
        self.assertIs(p.GetFiles(),paths)
        self.assertIs(p._file_thumbnail_list,p.files)

    def test_unrelated_file_change_does_not_invalidate_active_metadata(self):
        p=printer(snapshot());s=MoonrakerSubscription('http://localhost:7125',autostart=False)
        self.addCleanup(s.close);s._epoch=p.state.epoch;p.subscription=s
        p.job_Info={k:dict(v) for k,v in p.job_Info.items()}
        p.job_Info['print_stats'].update(state='printing',filename='part.gcode')
        p.getREST=Mock(return_value={'result':{'estimated_time':3600}})
        p._refresh_print_metadata();before=dict(p._current_print_metadata())
        s._notification({'method':'notify_filelist_changed','params':[{'action':'create_file','item':{'root':'gcodes','path':'other.gcode'}}]})
        p.state=replace(p.state,file_revision=s._file_revision)
        p._refresh_print_metadata()
        self.assertEqual(p.getREST.call_count,1)
        self.assertEqual(p._current_print_metadata(),before)
        pending=Future();p._read_worker=Mock();p._read_worker.submit.return_value=pending
        s._notification({'method':'notify_filelist_changed','params':[{'action':'modify_file','item':{'root':'gcodes','path':'part.gcode'}}]})
        p._refresh_print_metadata()
        self.assertEqual(p._current_print_metadata(),before)
        pending.set_exception(OSError('temporary'))
        p._refresh_print_metadata()
        self.assertEqual(p._current_print_metadata(),before)

    def test_file_change_history_is_bounded_and_directory_changes_invalidate(self):
        s=MoonrakerSubscription('http://localhost:7125',autostart=False)
        for i in range(200):
            s._notification({'method':'notify_filelist_changed','params':[{'action':'create_file','item':{'root':'gcodes','path':str(i)}}]})
        self.assertEqual(len(s._file_changes),128)
        before=s.file_identity('nested/part.gcode')
        s._notification({'method':'notify_filelist_changed','params':[{'action':'delete_dir','item':{'root':'gcodes','path':'nested'}}]})
        self.assertNotEqual(before,s.file_identity('nested/part.gcode'))
        s.close()
