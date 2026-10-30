"""Purpose-led Graphite Maintenance UI for the 272x480 encoder-only panel.

Presentation is separate from the trusted controllers. Only an explicit action
advances a workflow; observations have no timeout. No I/O in drawing/navigation.
"""

from petrel.features.maintenance.ui.flow import MaintenanceFlowMixin
from petrel.features.maintenance.ui.screens import MaintenanceScreensMixin
from petrel.features.maintenance.ui.records import MaintenanceRecordsMixin


class MaintenanceViewMixin(MaintenanceFlowMixin, MaintenanceScreensMixin, MaintenanceRecordsMixin):
    def _trace_maintenance_ui(self,kind='tick',event=None,title=None,entries=None):
        trace=getattr(self.pd,'maintenance_test_trace',None)
        if trace is not None and trace.active:
            trace.ui(self,kind,event,title,entries)

    def _maintenance_init(self):
        if not hasattr(self,'_maintenance_history'):
            self._maintenance_history=[]
            self._maintenance_page='root'
            self._maintenance_selection=0
            self._maintenance_report_position=0
            self._maintenance_context=None
            self._maintenance_frame=None
            self._maintenance_regions={}
            self._maintenance_notice=''
            self._maintenance_origin=None
            self._maintenance_records_future=None
            self._maintenance_records_data=((),())
            self._maintenance_records_ready=False
            self._maintenance_records_identity=None
            self._maintenance_records_request_identity=None
            self._maintenance_record_errors=0
            self._maintenance_reference_future=None
            self._maintenance_records_return='service'
            self._maintenance_records_background=False
            self._maintenance_records_failed=False
            self._maintenance_records_refresh_at=0.
            self._maintenance_sensor_future=None
            self._maintenance_sensor_identity=None

    def Enter_Maintenance_Menu(self):
        self._maintenance_init()
        self.checkkey=self.MaintenanceMenu
        self._maintenance_history=[]
        self._maintenance_context=None
        self._maintenance_frame=None
        self._maintenance_regions={}
        self._maintenance_show('root')
        self._maintenance_records_refresh_at=0.
        self._maintenance_prefetch_records()
