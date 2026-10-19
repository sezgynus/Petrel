"""Second-audit capacity and exactly-once local shutdown persistence (CI)."""
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import tempfile
import unittest
import maintenance_records as records
from maintenance_records import MaintenanceBook, read_json, write_json
from background_reads import ReadWorker
from test_maintenance_ui_services import DeferredWorker


class ReauditRecordTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        context=patch('maintenance_records.root',return_value=self.root)
        context.start();self.addCleanup(context.stop)

    def state(self):
        return NS(epoch=1,software_version='test',settings={},ready=True,status={})

    def result(self):
        return NS(feature_id='F01',device='fan',status='PASSED_USER',reason='observed',evidence=())

    def seed_usage(self, count):
        values={'fan_generic old%d'%i:float(i) for i in range(count)}
        write_json('maintenance-usage.json',{'version':1,'sampled_on_s':values,
            'sampled_print_s':10.,'counter_id':'a'*32})
        return values

    def test_full_ledger_rejects_new_name_without_breaking_existing_or_print_usage(self):
        original=self.seed_usage(32);book=MaintenanceBook(DeferredWorker())
        book._usage={'fan_generic new':5.,'fan_generic old0':2.,'@printing':3.}
        with self.assertLogs(level='WARNING'):book.flush()
        first=read_json('maintenance-usage.json',{})
        self.assertEqual(len(first['sampled_on_s']),32)
        self.assertNotIn('fan_generic new',first['sampled_on_s'])
        self.assertEqual(first['sampled_on_s']['fan_generic old0'],2.)
        self.assertEqual(first['sampled_print_s'],13.)
        self.assertEqual(first['counter_id'],'a'*32);self.assertGreater(book.errors,0)
        book._usage={'@printing':2.};book.flush()
        second=read_json('maintenance-usage.json',{})
        self.assertEqual(second['sampled_print_s'],15.)
        self.assertEqual(second['counter_id'],first['counter_id'])

    def test_legacy_oversized_batch_keeps_all_existing_values_and_identity(self):
        original=self.seed_usage(33);book=MaintenanceBook(DeferredWorker())
        book._usage={'fan_generic new':1.,'@printing':2.}
        with self.assertLogs(level='WARNING'):book.flush()
        data=read_json('maintenance-usage.json',{})
        self.assertEqual(data['sampled_on_s'],original)
        self.assertEqual(data['counter_id'],'a'*32)
        self.assertEqual(data['sampled_print_s'],12.)
        book.flush()  # No persistent read/write capacity failure loop.

    def test_last_free_slot_is_admitted_but_next_name_is_not(self):
        self.seed_usage(31);book=MaintenanceBook(DeferredWorker())
        book._usage={'fan_generic one':1.,'fan_generic two':2.}
        with self.assertLogs(level='WARNING'):book.flush()
        data=book.service_counters()['sampled_on_s']
        self.assertEqual(len(data),32)
        self.assertEqual(data['fan_generic one'],1.)
        self.assertNotIn('fan_generic two',data)

    def test_cancelled_queued_record_is_written_once_when_backend_worker_closes(self):
        worker=ReadWorker(timeout=.01);entered,release=Event(),Event()
        self.addCleanup(worker.close);self.addCleanup(release.set)
        def blocked():entered.set();release.wait(4)
        first=worker.submit(blocked,queue_timeout=2)
        self.assertTrue(entered.wait(1))
        book=MaintenanceBook(worker);book.record(self.result(),2,self.state())
        future=book._record_futures[0]
        self.assertFalse(worker.close())
        self.assertTrue(future.cancelled())
        book.close();book.close()
        self.assertEqual(len(read_json('maintenance-history.json',{})['records']),1)
        release.set();first.result(1);worker.close()
        self.assertEqual(len(read_json('maintenance-history.json',{})['records']),1)
        self.assertFalse(book._record_futures)

    def test_close_waits_for_started_local_write_without_duplicate(self):
        worker=ReadWorker(timeout=2);self.addCleanup(worker.close)
        entered,release=Event(),Event();self.addCleanup(release.set)
        book=MaintenanceBook(worker);original=records.write_json;calls=[]
        def write(name,data):
            if name=='maintenance-history.json':
                calls.append(name);entered.set();release.wait(2)
            return original(name,data)
        with patch('maintenance_records.write_json',side_effect=write):
            book.record(self.result(),2,self.state())
            self.assertTrue(entered.wait(1))
            closer=Thread(target=book.close);closer.start()
            release.set();closer.join(2)
            self.assertFalse(closer.is_alive())
        self.assertEqual(len(calls),1)
        self.assertEqual(len(read_json('maintenance-history.json',{})['records']),1)

    def test_failed_attempt_is_reported_without_replay_and_post_close_record_is_rejected(self):
        worker=DeferredWorker();book=MaintenanceBook(worker)
        book.record(self.result(),2,self.state())
        original=records.write_json;calls=[]
        def fail_history(name,data):
            if name=='maintenance-history.json':calls.append(name);raise OSError('disk')
            return original(name,data)
        with patch('maintenance_records.write_json',side_effect=fail_history):
            with self.assertLogs(level='WARNING'):book.close()
        self.assertEqual(len(calls),1);self.assertGreater(book.errors,0)
        queued=len(worker.work);book.record(self.result(),2,self.state())
        self.assertEqual(len(worker.work),queued)
