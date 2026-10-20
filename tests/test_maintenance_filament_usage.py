"""Native Moonraker history is read on demand and resets rotate identity."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from maintenance_filament_usage import read_totals, recorded_filament
from maintenance_care import reminder_default


class NativeFilamentHistoryTests(unittest.TestCase):
    def test_validated_native_mm_and_jobs(self):
        body={'result':{'job_totals':{'total_jobs':3,'total_filament_used':23550}}}
        self.assertEqual(read_totals(body),(23550.0,3))
        for value in (-1,True,'22',float('nan'),float('inf')):
            body['result']['job_totals']['total_filament_used']=value
            with self.assertRaises(ValueError): read_totals(body)

    def test_counter_identity_persists_and_changes_on_moonraker_reset(self):
        with tempfile.TemporaryDirectory() as td,patch('maintenance_records.root',return_value=Path(td)):
            client=NS(request=Mock(return_value={'result':{'job_totals':{
                'total_jobs':4,'total_filament_used':12000}}}))
            first=recorded_filament(client)
            self.assertEqual(first['filament_mm'],{'extruder':12000.0})
            self.assertEqual(recorded_filament(client)['filament_counter_id'],first['filament_counter_id'])
            client.request.return_value={'result':{'job_totals':{
                'total_jobs':5,'total_filament_used':15000}}}
            second=recorded_filament(client)
            self.assertEqual(second['filament_counter_id'],first['filament_counter_id'])
            client.request.return_value={'result':{'job_totals':{
                'total_jobs':0,'total_filament_used':0}}}
            reset=recorded_filament(client)
            self.assertNotEqual(reset['filament_counter_id'],first['filament_counter_id'])
            client.request.assert_called_with('GET','/server/history/totals',request_timeout=2.0)

    def test_incomplete_response_never_writes_a_zero(self):
        with tempfile.TemporaryDirectory() as td,patch('maintenance_records.root',return_value=Path(td)):
            client=NS(request=Mock(return_value={'result':{'job_totals':{}}}))
            with self.assertRaises(ValueError): recorded_filament(client)
            self.assertFalse((Path(td)/'maintenance-filament-history.json').exists())

    def test_different_extruder_tasks_have_distinct_defaults(self):
        self.assertEqual(reminder_default('extruder','nozzle','filament_mm'),500)
        self.assertEqual(reminder_default('extruder','heating','filament_mm'),1000)
        self.assertEqual(reminder_default('extruder','filament_feed','filament_mm'),1000)


    def test_existing_records_use_native_counter_without_rebasing(self):
        from maintenance_assessment_store import ServicePolicy
        from maintenance_ui_records import request
        from test_maintenance_ui_services import DeferredWorker
        policy=ServicePolicy('nozzle','extruder','filament_mm',20000,'user')
        observed={'length':50000.,'id':'a'*32}
        calls=[]
        def provider():
            calls.append(1)
            return dict(filament_mm={'extruder':observed['length']},
                        filament_counter_id=observed['id'],
                        available_metrics=(('extruder','filament_mm'),))
        with tempfile.TemporaryDirectory() as td,patch(
                'maintenance_ui_records.Path.home',return_value=Path(td)):
            worker=DeferredWorker()
            def run(op):
                future=request(worker,op,policy=policy if op!='load' else None,
                               devices=('extruder',),filament_provider=provider)
                worker.run()
                return future.result()[0][0]
            first=run('save_policy')
            self.assertEqual(first[1]['_sampled_elapsed_s'],0)
            self.assertEqual(first[2],'unknown')
            observed['length']=68000
            current=run('load')
            self.assertEqual(current[1]['_sampled_elapsed_s'],18000)
            observed['length']=75000
            self.assertEqual(run('load')[2],'due')
            observed['id']='b'*32
            paused=run('load')
            self.assertEqual(paused[2],'unknown')
            self.assertTrue(paused[1]['_tracking_paused'])
            self.assertEqual(len(calls),4)

    def test_only_single_extruder_receives_printer_wide_filament_basis(self):
        from test_capabilities import display, snapshot
        view=display(snapshot())
        self.assertIn('filament_mm',view.pd.maintenance_service_bases('extruder'))
        raw=snapshot()
        raw['objects'].append('extruder1')
        other=display(raw)
        self.assertNotIn('filament_mm',other.pd.maintenance_service_bases('extruder'))
        self.assertNotIn('filament_mm',other.pd.maintenance_service_bases('extruder1'))
        self.assertNotIn('filament_mm',view.pd.maintenance_service_bases('heater_bed'))


if __name__ == '__main__':
    unittest.main()
