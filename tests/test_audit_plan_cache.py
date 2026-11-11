import unittest
from dataclasses import replace
from unittest.mock import patch
from petrel.features.maintenance.discovery.discovery import MaintenanceSnapshot,DeviceCapabilities,INFORMATION,_add
from petrel.features.maintenance.execution.executor import read_only_adapters
import petrel.features.maintenance.execution.planner as planner

class VisiblePlanCache(unittest.TestCase):
    def setUp(self): planner.clear_plan_cache();self.addCleanup(planner.clear_plan_cache)
    def snapshot(self,epoch=1):
        return MaintenanceSnapshot(epoch,(DeviceCapabilities('extruder','heater',_add(0,'H11',INFORMATION)),),config_marker=8)

    def test_repeated_availability_reuses_rows_but_new_snapshot_rebuilds(self):
        snap=self.snapshot();registry=read_only_adapters()
        expected=planner.visible_plan(planner.build_plan(snap,registry))
        first=planner.registered_plan(snap,registry)
        self.assertEqual(first,expected)
        with patch.object(planner,'build_plan',side_effect=AssertionError('repeat scan')):
            self.assertIs(planner.registered_plan(snap,read_only_adapters()),first)
        fresh=planner.registered_plan(replace(snap,epoch=2),registry)
        self.assertEqual(fresh[0].epoch,2)
        self.assertIsNot(first,fresh)
        planner.clear_plan_cache()
        self.assertFalse(planner._PLAN_CACHE)
        self.assertIsNone(planner._PLAN_SNAPSHOT)

    def test_large_inventory_does_not_escape_row_retention_limit(self):
        snap=MaintenanceSnapshot(1,tuple(DeviceCapabilities('heater_generic h'+str(i),'heater',
            _add(0,'H11',INFORMATION)) for i in range(600)),config_marker=1)
        rows=planner.registered_plan(snap,read_only_adapters())
        self.assertEqual(len(rows),600)
        self.assertLessEqual(sum(map(len,planner._PLAN_CACHE.values())),512)
