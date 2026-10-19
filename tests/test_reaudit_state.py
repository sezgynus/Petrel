"""Second-audit resort, epoch memory ownership and maintenance scheduling (CI)."""
from concurrent.futures import Future
from threading import current_thread
from types import SimpleNamespace as NS
from unittest.mock import Mock
import gc
import unittest
import weakref
import test_files as files
from test_capabilities import printer, snapshot
from test_maintenance_ui_services import DeferredWorker
from test_regressions import ui
from background_reads import ReadWorker
from ui_events import UIEventLoop


class ReauditStateTests(unittest.TestCase):
    def test_preference_change_prepares_private_sorted_list_on_worker(self):
        p=files.FileTests().backend(['c.gcode','b.gcode','a.gcode'])
        original=p.files;paths=p._files_paths_snapshot
        worker=ReadWorker(timeout=2);self.addCleanup(worker.close);p._read_worker=worker
        p._file_sort_refresh_at=0
        p.client.get.return_value={'result':{'value':{'sortBy':'filename','sortDesc':True}}}
        owner=current_thread();threads=[];sort=p._sort_files
        def observed(*args,**kwargs):threads.append(current_thread());return sort(*args,**kwargs)
        p._sort_files=observed
        changed=p.refresh_file_sort()
        if not changed and 'file_sort' in p._read_jobs:
            p._read_jobs['file_sort'][1].result(1)
            changed=p.refresh_file_sort()
        if not changed:
            p._file_sort_pending[2].result(1)
            self.assertTrue(p.refresh_file_sort())
        self.assertEqual(p._files_paths_snapshot,('c.gcode','b.gcode','a.gcode'))
        self.assertIsNot(p.files,original)
        self.assertEqual(tuple(item['path'] for item in original),paths)
        self.assertTrue(threads);self.assertTrue(all(t is not owner for t in threads))
        self.assertIs(p._file_thumbnail_list,p.files)

    def test_late_resort_cannot_overwrite_replaced_list(self):
        p=files.FileTests().backend(['b.gcode','a.gcode']);worker=DeferredWorker();p._read_worker=worker
        p.client.get.return_value={'result':{'value':{'sortBy':'filename','sortDesc':True}}}
        p._file_sort_refresh_at=0
        p.refresh_file_sort();worker.run();p.refresh_file_sort()
        future=p._file_sort_pending[2];future.set_running_or_notify_cancel()
        replacement=[{'path':'new.gcode'}];p.files=replacement
        self.assertFalse(p.refresh_file_sort())
        worker.run()
        self.assertIs(p.files,replacement)
        self.assertNotEqual(p.file_sort,('filename',True))

    def test_disconnect_releases_backend_and_ui_owners_before_reload(self):
        class FileList(list):pass
        class Index(dict):pass
        v=files.FileTests().display(['a.gcode','b.gcode'])
        old=FileList(v.pd.files);index=Index(v.pd._file_thumbnail_keys)
        v.pd.files=v.pd._file_thumbnail_list=old
        v.pd._file_thumbnail_keys=v._thumbnail_keys=index
        old_ref,index_ref=weakref.ref(old),weakref.ref(index)
        v.pd.subscription.snapshot.return_value={'state':'disconnected','epoch':2,'revision':2,'status':{}}
        v._update_ui_state()
        del old,index
        gc.collect()
        self.assertIsNone(old_ref());self.assertIsNone(index_ref())
        self.assertEqual(v.pd.files,[]);self.assertEqual(v.pd._files_paths_snapshot,())
        self.assertEqual(v._file_paths,());self.assertEqual(v._thumbnail_keys,{})
        self.assertFalse(v._thumbnail_cache.valid)
        v.pd.subscription.snapshot.return_value=snapshot()
        v._update_ui_state()
        self.assertEqual(v.pd.GetFiles(),('a.gcode','b.gcode'))

    def view(self):
        v=ui.PetrelDisplay.__new__(ui.PetrelDisplay)
        v.pd=Mock();v.pd.update_variable.return_value=False
        v.pd.maintenance_pulse=NS(pending=True,phase='running')
        v.pd.maintenance_reader=NS(pending=False)
        v.pd.poll_maintenance_physical.return_value=None
        v._loop=UIEventLoop(lambda:None,lambda e:None,lambda:None,lambda:None)
        v.lcd=Mock();v._uart_online=True;v._boot_active=False
        v._poll_panel_power=Mock();v._sync_case_light_tracking=Mock()
        v._power_hold_tick=Mock(return_value=False);v._power_popup_tick=Mock(return_value=False)
        v._next_uart_probe=float('inf');v._display_idle_tick=Mock();v._draw_header_clock=Mock(return_value=False)
        v.checkkey=v.MaintenanceMenu
        return v

    def test_normal_tick_updates_model_once_and_retains_100ms_operation_cadence(self):
        v=self.view()
        v.EachMomentUpdate=lambda:v._update_ui_state()
        v._ui_tick()
        v.pd.update_variable.assert_called_once()
        v.pd.poll_maintenance_physical.assert_called_once()
        self.assertEqual(v._loop._interval,.1)
        # Inputs outside the tick must observe fresh state.
        v._update_ui_state();self.assertEqual(v.pd.update_variable.call_count,2)

    def test_overlay_and_uart_return_still_advance_once_and_fast_render_is_preserved(self):
        for mode in ('hold','popup','uart','fast'):
            with self.subTest(mode=mode):
                v=self.view()
                if mode=='hold':v._power_hold_tick.return_value=True
                if mode=='popup':
                    def popup():v._update_ui_state();return True
                    v._power_popup_tick=popup
                if mode=='uart':v._uart_online=False;v._ensure_uart=Mock()
                if mode=='fast':
                    v._power_hold_tick=lambda:v._loop.set_interval(.02) or True
                v._ui_tick()
                v.pd.update_variable.assert_called_once()
                v.pd.poll_maintenance_physical.assert_called_once()
                self.assertLessEqual(v._loop._interval,.1)
                if mode=='fast':self.assertEqual(v._loop._interval,.02)
