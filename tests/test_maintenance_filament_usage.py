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


if __name__ == '__main__':
    unittest.main()
