"""Same-session sampled counters refresh without UI disk work or writes."""
import unittest
from concurrent.futures import Future
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from test_capabilities import display, snapshot
from petrel.features.maintenance.assessment.store import ServicePolicy

class CareRefresh(unittest.TestCase):
    def make(self):
        d=display(snapshot());d.checkkey=d.MaintenanceMenu;d._maintenance_init()
        d.pd.maintenance_pulse=NS(pending=False,phase=None)
        d.pd.maintenance_reader=NS(pending=False)
        d._maintenance_records_ready=True
        d._maintenance_records_identity=d._maintenance_identity()
        d._maintenance_records_refresh_at=100.
        d.Draw_Maintenance_Menu=Mock()
        d.pd.maintenance_ui_records=Mock(return_value=Future())
        return d

    def test_reentry_refreshes_even_with_unchanged_epoch(self):
        d=self.make()
        with patch.dict(d._poll_maintenance_ui.__globals__,{'monotonic':lambda:50.}), \
                patch.dict(d._maintenance_prefetch_records.__globals__,{'monotonic':lambda:50.}):
            d.Enter_Maintenance_Menu()
        d.pd.maintenance_ui_records.assert_called_once_with('load',policy=None,history=False)
        self.assertTrue(d._maintenance_records_ready)

    def test_due_refresh_is_throttled_and_updates_open_task(self):
        d=self.make();p=ServicePolicy('inspect_clean','fan','sampled_on_s',100.,'user')
        last={'timestamp':1.,'counter':0.,'counter_id':'a'}
        d._maintenance_page='service_task';d._maintenance_context=(p,last,'unknown')
        d._maintenance_records_data=(((p,last,'unknown'),),())
        with patch.dict(d._poll_maintenance_ui.__globals__,{'monotonic':lambda:99.}), \
                patch.dict(d._maintenance_prefetch_records.__globals__,{'monotonic':lambda:99.}):
            d._poll_maintenance_ui()
        d.pd.maintenance_ui_records.assert_not_called()
        with patch.dict(d._poll_maintenance_ui.__globals__,{'monotonic':lambda:100.}), \
                patch.dict(d._maintenance_prefetch_records.__globals__,{'monotonic':lambda:100.}):
            d._poll_maintenance_ui();d._poll_maintenance_ui()
            future=d._maintenance_records_future
            future.set_result((((p,last,'due'),),()))
            d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_context[2],'due')
        self.assertEqual(d._maintenance_records_refresh_at,160.)
        self.assertEqual(d._maintenance_page,'service_task')
        self.assertEqual(d.pd.maintenance_ui_records.call_count,1)
