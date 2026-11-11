"""Existing PrinterData methods grouped by responsibility."""
import logging
from petrel.features.maintenance.execution.guided import guided_plan
from petrel.features.maintenance.domains.system import travel_profile
from petrel.features.maintenance.domains.thermal.controller import thermal_plan


class MaintenancePrinterMixin:
    def toggle_maintenance_test_recording(self):
        if self.maintenance_pulse.pending or self.maintenance_reader.pending:
            return False
        trace = getattr(self,'maintenance_test_trace',None)
        if trace is not None and trace.active:
            trace.stop()
        else:
            if trace is None:
                from petrel.features.maintenance.diagnostics.test_trace import TestTrace
                trace = self.maintenance_test_trace = TestTrace(self)
            trace.start()
            trace.tick(self.state)
        return True

    def maintenance_test_recording_label(self):
        trace = getattr(self,'maintenance_test_trace',None)
        return trace.label if trace is not None else 'Start test recording'

    def export_maintenance_test_recording(self):
        trace = getattr(self,'maintenance_test_trace',None)
        return trace.exported() if trace is not None else None

    def _note_maintenance_state(self,state):
        book = getattr(self,'maintenance_book',None)
        if book is not None:
            book.note(state,snapshot=getattr(getattr(self,'maintenance',None),'snapshot',None))
        # TEMPORARY MAINTENANCE TEST TRACE
        trace = getattr(self,'maintenance_test_trace',None)
        if trace is not None:
            trace.tick(state)

    def maintenance_integrations(self,state):
        services = ['maintenance.records','maintenance.usage_counters','maintenance.report_export']
        if travel_profile(state):
            services.append('maintenance.travel_counter')
        if callable(getattr(self,'_maintenance_panel_api',None)):
            services.extend(('petrel.uart_diagnostics','petrel.encoder_diagnostics',
                             'petrel.lcd_diagnostics','petrel.backlight'))
        return tuple(services)

    def maintenance_local_read(self,feature):
        if feature in ('S11','S12','S20'):
            return self.maintenance_book.read(feature)
        if feature in ('S14','S15','S16') and callable(getattr(self,'_maintenance_panel_api',None)):
            data = self._maintenance_panel_api('info')
            prefix = 'gpio_' if feature=='S15' else None
            keys = ('startup_assets_synced','uart_epoch') if feature=='S16' else (
                    tuple(k for k in data if k.startswith(prefix)) if prefix else
                    tuple(k for k in data if not k.startswith('gpio_')))
            return tuple((k,data[k]) for k in keys if type(data.get(k)) in (int,float,bool))
        return ()

    def _record_maintenance_result(self,result,method,plan=None):
        if result is not None:
            book = getattr(self,'maintenance_book',None)
            if book is not None:
                book.record(result,method,self.state,plan)
            assessment = getattr(self,'maintenance_assessment',None)
            if assessment is not None:
                try:
                    assessment.ingest(result,method,self.state)
                except (ValueError, TypeError, AttributeError):
                    logging.warning('Maintenance assessment evidence rejected')
        return result

    def maintenance_ui_records(self, operation, policy=None, history=False):
        from petrel.features.maintenance.records.ui_requests import request
        rows=tuple(self.maintenance_guided_plan())+tuple(self.maintenance_read_plan())
        devices=self.maintenance_service_devices(rows)
        return request(self._maintenance_worker,operation,policy=policy,devices=devices,history=history,
            usage_provider=self.maintenance_book.service_counters,
            filament_provider=self.maintenance_filament_usage)

    def maintenance_filament_usage(self):
        from petrel.features.maintenance.records.filament_usage import recorded_filament
        return recorded_filament(self.client)

    def maintenance_sensor_devices(self):
        from petrel.features.maintenance.domains.sensors.diagnostics import devices
        return devices(self.maintenance.snapshot)

    def maintenance_sensor_diagnostic(self,device):
        from petrel.features.maintenance.domains.sensors.diagnostics import read
        if device not in self.maintenance_sensor_devices():
            raise ValueError('sensor_device_no_longer_available')
        state = self.state
        return self._maintenance_worker.submit(
            lambda: read(self.client, state, device), queue_timeout=8)

    def maintenance_service_bases(self,device):
        bases=('calendar_s','sampled_print_s')
        # History totals are printer-wide, not individual nozzle usage.
        extruders=tuple(x for x in self.state.objects if x=='extruder' or
                        x.startswith('extruder') and x[8:].isdigit())
        if device=='extruder' and extruders==('extruder',):
            bases += ('filament_mm',)
        from petrel.features.maintenance.records.travel import installed, AXES, travel_device
        if travel_device(device) in AXES and installed(self.state):
            return bases+('travel_mm',)
        from petrel.features.maintenance.records.sensor_usage import event_sample
        sample=event_sample(self.state)
        if sample is not None and device in sample[1] and device not in sample[3]:
            bases += ('trigger_count',)
        snapshot=self.maintenance.snapshot
        return bases+tuple(dict.fromkeys(m.metric_id for m in getattr(snapshot,'usage_metrics',())
                                          if m.device==device))

    def maintenance_service_devices(self,rows=()):
        snapshot=self.maintenance.snapshot
        from petrel.features.maintenance.records.travel import installed, AXES
        return tuple(dict.fromkeys(
            (AXES if installed(self.state) else ())+
            tuple(getattr(snapshot,'care_devices',()))+
            tuple(d.name for d in getattr(snapshot,'devices',()))+
            tuple(m.device for m in getattr(snapshot,'usage_metrics',()))+
            tuple(r.device for r in rows if r.device is not None)))

    def maintenance_reference(self,operation,result,*,relative_limit=None,confirmed=False):
        from petrel.features.maintenance.assessment.reference import request
        snapshot=self.maintenance.snapshot
        identity=(getattr(snapshot,'epoch',None),getattr(snapshot,'config_marker',None))
        operation_id=getattr(result,'operation_id','')
        if not self.maintenance_assessment.current_operation(snapshot,operation_id):
            raise ValueError('reference_measurement_stale')
        def current():
            live=self.maintenance.snapshot
            return (self.state.ready and live is not None and
                (live.epoch,live.config_marker)==identity)
        return request(self._maintenance_worker,operation,result,self.state,
            relative_limit=relative_limit,confirmed=confirmed,current=current)

    def accept_maintenance_reference(self,result):
        if not self.maintenance_assessment.current_operation(self.maintenance.snapshot,result.operation_id):
            return False
        if result.reset_device is not None:
            self.maintenance_assessment.invalidate_trends(result.reset_device)
        if result.finding is None: return True
        return self.maintenance_assessment.accept_trend(
            self.maintenance.snapshot,result.operation_id,result.finding)

    def _maintenance_assessment_rows(self):
        from petrel.features.maintenance.domains.thermal.controller import thermal_plan
        rows=tuple(self.maintenance_read_plan())+tuple(self.maintenance_guided_plan())
        return tuple(dict.fromkeys(rows+thermal_plan(self.maintenance.snapshot)))

    def maintenance_assessment_details(self, **policies):
        rows = self._maintenance_assessment_rows()
        return self.maintenance_assessment.detailed_report(
            self.maintenance.snapshot, rows, **policies)

    def maintenance_assessment_report(self):
        rows = self._maintenance_assessment_rows()
        return self.maintenance_assessment.report(self.maintenance.snapshot, rows)

    def maintenance_read_plan(self):
        return self.maintenance_reader.available()

    def maintenance_guided_plan(self):
        # Passive target discovery only; not an actuation authorization.
        owner = getattr(self, 'maintenance_pulse', None)
        return owner.available() if owner is not None else guided_plan(self.maintenance.snapshot)

    def start_maintenance_physical(self, feature_id, device=None, **kwargs):
        return self.maintenance_pulse.start(feature_id, device, **kwargs)

    def poll_maintenance_physical(self):
        row = getattr(self.maintenance_pulse,'_row',None)
        return self._record_maintenance_result(self.maintenance_pulse.poll(),getattr(row,'method',None),row)

    def confirm_maintenance_physical(self):
        return self.maintenance_pulse.confirm()

    def observe_maintenance_physical(self, seen):
        row = getattr(self.maintenance_pulse,'_row',None)
        return self._record_maintenance_result(self.maintenance_pulse.observe(seen),getattr(row,'method',None),row)

    def confirm_maintenance_f12_stopped(self):
        row = getattr(self.maintenance_pulse,'_row',None)
        result,reason = self.maintenance_pulse.f12_confirm_stopped()
        if result is not None and type(result) is not bool:
            self._record_maintenance_result(result,getattr(row,'method',None),row)
        return result,reason

    def cancel_maintenance_physical(self):
        row = getattr(self.maintenance_pulse,'_row',None)
        return self._record_maintenance_result(self.maintenance_pulse.cancel(),getattr(row,'method',None),row)

    def start_maintenance_read(self, feature_id, timeout=8.0, device=None):
        return self.maintenance_reader.start(feature_id, timeout=timeout, device=device)

    def poll_maintenance_read(self):
        row = self.maintenance_reader._row
        return self._record_maintenance_result(self.maintenance_reader.poll(),16,row)

    def cancel_maintenance_read(self):
        row = self.maintenance_reader._row
        return self._record_maintenance_result(self.maintenance_reader.cancel(),16,row)
