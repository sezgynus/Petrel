"""CI-only coverage and resource ownership regressions."""
from pathlib import Path
from threading import Event
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from concurrent.futures import Future
import tempfile
import unittest
from background_reads import ReadWorker
from maintenance_records import MaintenanceBook, read_json
from test_maintenance_ui_services import DeferredWorker
from test_capabilities import printer, snapshot
from software_update import SoftwareUpdate

class AuditResourceTests(unittest.TestCase):
    def test_unobserved_devices_have_no_fabricated_zero_counter(self):
        with tempfile.TemporaryDirectory() as tmp, patch('maintenance_records.Path.home',return_value=Path(tmp)):
            book = MaintenanceBook(DeferredWorker())
            cfg = {'fan_generic optional': {}, 'fan': {}}
            state = NS(ready=True,epoch=1,objects=tuple(cfg),settings=cfg,status={'fan':{'speed':0}})
            book.note(state,now=0)
            counters = book.service_counters()['sampled_on_s']
            self.assertNotIn('fan_generic optional', counters)
            self.assertEqual(counters['fan'], 0)
            state.status['fan_generic optional'] = {'speed':1}
            book.note(state,now=1);book.note(state,now=2)
            self.assertEqual(book.service_counters()['sampled_on_s']['fan_generic optional'],1)

    def test_orderly_close_preserves_tail_without_periodic_deadline(self):
        with tempfile.TemporaryDirectory() as tmp, patch('maintenance_records.Path.home',return_value=Path(tmp)):
            book=MaintenanceBook(DeferredWorker())
            state=NS(ready=True,epoch=1,objects=('fan',),settings={'fan':{}},status={'fan':{'speed':1}})
            book.note(state,now=0);book.note(state,now=1)
            book.close()
            self.assertEqual(read_json('maintenance-usage.json',{})['sampled_on_s']['fan'],1)

    def test_worker_keeps_resource_until_running_io_exits(self):
        entered, release, closed = Event(), Event(), Event()
        worker=ReadWorker(timeout=.01)
        def work():
            entered.set();release.wait(3)
            self.assertFalse(closed.is_set())
        f=worker.submit(work,queue_timeout=3)
        self.assertTrue(entered.wait(1))
        worker.on_stopped(closed.set)
        self.assertFalse(worker.close())
        self.assertFalse(closed.is_set())
        release.set();f.result(1)
        self.assertTrue(closed.wait(1))
        worker.close()

    def test_update_lane_is_lazy_and_does_not_occupy_maintenance_worker(self):
        p=printer(snapshot())
        u=SoftwareUpdate(p)
        self.assertIsNone(u._worker)
        p._maintenance_worker.submit=Mock(side_effect=AssertionError('shared lane'))
        with patch('software_update.ReadWorker') as factory:
            lane=factory.return_value
            lane.submit.return_value=Future()
            u.start()
            lane.submit.assert_called_once()
            p._maintenance_worker.submit.assert_not_called()
            u.close()
            self.assertTrue(u.future.cancelled())
            lane.close.assert_called_once()

    def test_update_close_prevents_followup_requests_without_replaying(self):
        p=printer(snapshot());worker=DeferredWorker()
        u=SoftwareUpdate(p,worker=worker)
        with patch('software_update.MoonrakerClient') as factory:
            client=factory.return_value
            def get(path):
                u._closed.set()
                return {'result':{'version_info':{'Petrel':{'is_valid':True,'current_hash':'a','remote_hash':'b'}}}}
            client.get.side_effect=get
            u.start();worker.run();u.poll()
            client.request.assert_not_called()
            client.close.assert_called_once()
