"""Maintenance navigation, explicit actions and operation progress."""
from types import SimpleNamespace
from time import monotonic
from petrel.features.maintenance.records.care import tasks as care_tasks
from petrel.features.maintenance.ui.report import cached_report_rows, report_navigation


class MaintenanceFlowMixin:
    def _maintenance_back_home(self):
        self._maintenance_report_source=None
        self._maintenance_report_rows=()
        self._maintenance_report_position=0
        self._maintenance_history=[]
        self._maintenance_frame=None
        self._maintenance_page='root'
        self._maintenance_selection=0
        self.select_page.set(next(i for i,e in enumerate(self._home_entries()) if e[0]=='MAINTENANCE'))
        self.Goto_MainMenu()
        self.lcd.update()

    def _maintenance_show(self,page,selection=0):
        self._maintenance_init()
        if page!=self._maintenance_page:
            self._maintenance_report_position=0
            self._maintenance_report_source=None
            self._maintenance_report_rows=()
        self._maintenance_page=page
        self._maintenance_selection=selection
        self.Draw_Maintenance_Menu()
        self.lcd.update()

    def _maintenance_open(self,page,context=None):
        self._maintenance_init()
        self._maintenance_history.append((self._maintenance_page,self._maintenance_selection,self._maintenance_context))
        self._maintenance_context=context
        self._maintenance_report_position=0
        self._maintenance_notice=''
        self._maintenance_show(page)

    def _maintenance_back(self):
        self._maintenance_notice=''
        if self._maintenance_history:
            page,selection,context=self._maintenance_history.pop()
            self._maintenance_context=context
            self._maintenance_show(page,selection)
        else:
            self._maintenance_show('root')

    def _maintenance_complete(self,result):
        if result is None:
            return
        self._maintenance_result=result
        self._maintenance_notice=''
        self._maintenance_show('result')

    def _maintenance_dispatch(self,choice):
        action,value=choice.action,choice.value
        if action=='none': return
        if action in ('sensor_read','sensor_refresh'):
            if self._maintenance_sensor_future is not None: return
            try:
                self._maintenance_sensor_future=self.pd.maintenance_sensor_diagnostic(value)
                self._maintenance_sensor_identity=self._maintenance_identity()
            except Exception:
                return self._maintenance_open('notice',('Sensor unavailable',
                    ('The configuration or connection changed.','Return to the sensor list and retry.')))
            if action=='sensor_read': return self._maintenance_open('sensor_wait')
            return self._maintenance_show('sensor_wait')
        if action=='reference': return self._maintenance_open('reference',value)
        if action=='reference_limit': return self._maintenance_open('reference_limit',(value,20))
        if action=='reference_confirm': return self._maintenance_open('reference_confirm',value)
        if action=='reference_run':
            if self._maintenance_reference_future is not None: return
            operation,outcome,limit=value
            try:
                self._maintenance_reference_future=self.pd.maintenance_reference(
                    operation,outcome,relative_limit=limit,confirmed=True)
            except Exception:
                return self._maintenance_open('notice',('Reference unavailable',
                    ('Run a fresh compatible heating check.','No reference success is assumed.')))
            return self._maintenance_open('reference_wait')
        if action=='historical_result':
            record=value
            outcome=SimpleNamespace(feature_id=record.get('feature'),device=record.get('device'),
                status=record.get('status'),reason='Historical record: '+str(record.get('reason','')),
                evidence=tuple(record.get('evidence',())),restore_verified=record.get('restore_verified'))
            return self._maintenance_open('details',outcome)
        if action=='service_discard':
            self._maintenance_history=[('root',1,None)]
            self._maintenance_context=None
            return self._maintenance_show('service')
        if action=='service_add': return self._maintenance_open('service_devices')
        if action=='service_device':
            kinds=care_tasks(value)
            return self._maintenance_open('service_basis',(value,kinds[0])) if len(kinds)==1 else self._maintenance_open('service_kind',value)
        if action=='service_kind': return self._maintenance_open('service_basis',value)
        if action=='service_basis':
            from petrel.features.maintenance.records.care import reminder_default
            device,task,basis=value
            return self._maintenance_open('service_interval',
                (device,task,reminder_default(device,task,basis),basis))
        if action=='service_review':
            from petrel.features.maintenance.assessment.store import ServicePolicy
            device,task,amount=self._maintenance_context[:3]
            basis=self._maintenance_context[3] if len(self._maintenance_context)>3 else 'calendar_s'
            return self._maintenance_open('service_review',ServicePolicy(task,device,basis,
                amount*(86400 if basis=='calendar_s' else 1000 if basis in ('travel_mm','filament_mm') else
                        1 if basis in ('observed_trigger_count','trigger_count') else 3600),'user-defined interval'))
        if action=='service_task': return self._maintenance_open('service_task',value)
        if action=='service_confirm': return self._maintenance_open('service_confirm',value)
        if action=='service_remove_confirm': return self._maintenance_open('service_remove_confirm',value)
        if action=='service_remove': return self._maintenance_load_records('remove_policy',value)
        if action in ('service_save','service_complete'):
            return self._maintenance_load_records('save_policy' if action=='service_save' else 'complete',value)
        if action=='load_history': return self._maintenance_load_records(history=True)
        if action=='home': return self._maintenance_back_home()
        if action=='back': return self._maintenance_back()
        if action=='open': return self._maintenance_open(value)
        if action=='diagnostic_topic': return self._maintenance_open('diagnostic_topic',value)
        if action=='targets': return self._maintenance_open('targets',value)
        if action=='prepare': return self._maintenance_open('prepare',value)
        if action=='details': return self._maintenance_open('details',value)
        if action=='instructions': return self._maintenance_open('instructions',value)
        if action=='finding': return self._maintenance_open('finding',value)
        if action=='review':
            outcome=SimpleNamespace(status='OBSERVED',reason='Measured evidence',evidence=tuple(('value',x) for x in value))
            return self._maintenance_open('details',outcome)
        if action=='result_back':
            origin=getattr(self,'_maintenance_origin',None)
            if origin:
                self._maintenance_page,self._maintenance_selection,self._maintenance_context=origin
                self.Draw_Maintenance_Menu();self.lcd.update()
            else: self._maintenance_show('root')
            return
        if action in ('findings','service','history','leveling'):
            return self._maintenance_open(action)
        if action=='trace':
            self.pd.toggle_maintenance_test_recording()
            return self._maintenance_show('support',1)
        if action=='start' or action=='read':
            self._maintenance_origin=(self._maintenance_page,self._maintenance_selection,self._maintenance_context)
            row=value
            device=getattr(row, 'device', None)
            if action=='start':
                accepted,reason=self.pd.start_maintenance_physical(row.feature_id,device)
            else:
                accepted,reason=self.pd.start_maintenance_read(row.feature_id,device=device) if device is not None else self.pd.start_maintenance_read(row.feature_id)
            if accepted:
                self._maintenance_show('pulse' if action=='start' else 'reading')
            else:
                self._maintenance_complete(SimpleNamespace(feature_id=row.feature_id,device=device,status='BLOCKED',reason=reason))
            return
        if action=='confirm':
            accepted,reason=self.pd.confirm_maintenance_physical()
            if not accepted:
                self._maintenance_complete(SimpleNamespace(status='BLOCKED',reason=reason))
            else: self._maintenance_show('pulse')
            return
        if action=='cancel':
            result=self.pd.cancel_maintenance_physical()
            if result is not None: self._maintenance_complete(result)
            else: self._maintenance_show('pulse')
            return
        if action=='cancel_read':
            return self._maintenance_complete(self.pd.cancel_maintenance_read())
        if action=='choose':
            accepted,reason=self.pd.maintenance_pulse.choose(value)
            self._maintenance_notice='' if accepted else 'Step not accepted. Review preparation.'
            return self._maintenance_show('pulse')
        if action=='measure':
            self.pd.maintenance_pulse.begin_measurement()
            return self._maintenance_show('pulse')
        if action=='record':
            owner=self.pd.maintenance_pulse
            accepted,reason=owner.record_measurement(owner.measurement_value)
            self._maintenance_notice='' if accepted else 'Measurement not accepted. Review the value.'
            return self._maintenance_show('pulse')
        if action=='observe':
            result=self.pd.observe_maintenance_physical(value)
            if result is not None: self._maintenance_complete(result)
            else: self._maintenance_show('pulse')
            return
        if action=='fan_stop':
            result,reason=self.pd.confirm_maintenance_f12_stopped()
            if result is True: self._maintenance_show('pulse')
            elif result is not None and type(result) is not bool: self._maintenance_complete(result)
            else: self._maintenance_complete(SimpleNamespace(status='BLOCKED',reason=reason))
            return
        if action in ('load_services','history_read','export'):
            return self._maintenance_storage_action(action,value)

    def HMI_Maintenance_Menu(self):
        self._maintenance_init()
        event=self.get_encoder_state()
        if event==self.ENCODER_DIFF_NO: return
        owner=getattr(self.pd,'maintenance_pulse',None)
        if (self._maintenance_page=='pulse' and getattr(owner,'phase',None)=='measurement_edit'
                and event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW)):
            steps=max(1,int(getattr(self,'_menu_batch_steps',1)))
            owner.adjust_measurement(.01*steps*(1 if event==self.ENCODER_DIFF_CW else -1))
            self._maintenance_show('pulse');return
        if self._maintenance_page=='service_interval' and event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            device,task,days=self._maintenance_context[:3]
            tail=self._maintenance_context[3:]
            steps=max(1,int(getattr(self,'_menu_batch_steps',1)))
            # Slow turning keeps single-unit precision. Accelerated encoder
            # batches skip proportionally through thousands of metres/events.
            if steps>1:
                steps *= (1000 if days>=10000 else 100 if days>=1000 else
                          10 if days>=100 else 1)
            maximum=87600 if tail and tail[0]!='calendar_s' else 3650
            days=max(1,min(maximum,days+(steps if event==self.ENCODER_DIFF_CW else -steps)))
            self._maintenance_context=(device,task,days)+tail
            self.Draw_Maintenance_Menu();self.lcd.update();return
        if self._maintenance_page=='reference_limit' and event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            outcome,percent=self._maintenance_context
            steps=max(1,int(getattr(self,'_menu_batch_steps',1)))
            percent=max(1,min(100,percent+(steps if event==self.ENCODER_DIFF_CW else -steps)))
            self._maintenance_context=(outcome,percent)
            self.Draw_Maintenance_Menu();self.lcd.update();return
        screen=(getattr(self,'_maintenance_last_screen',None) if self._maintenance_frame is not None and self._maintenance_frame[1]==self._maintenance_page
                else None)
        rotating=event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW)
        if screen is None or not rotating: screen=self._maintenance_screen()
        choices=screen.choices
        if event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            steps=max(1,int(getattr(self,'_menu_batch_steps',1)))
            delta=steps if event==self.ENCODER_DIFF_CW else -steps
            if screen.kind=='report':
                from dataclasses import replace
                rows=cached_report_rows(self,screen)
                position,offset,selected,_=report_navigation(rows,choices,self._maintenance_report_position+delta)
                self._maintenance_report_position=position
                self._maintenance_selection=selected
                screen=replace(screen,report_offset=offset)
            else:
                self._maintenance_selection=max(0,min(max(0,len(choices)-1),self._maintenance_selection+delta))
            self.Draw_Maintenance_Menu(screen);self.lcd.update()
        elif event==self.ENCODER_DIFF_ENTER and choices:
            drawn=getattr(self,'_maintenance_drawn_choices',None)
            current=tuple((c.action,c.value) for c in choices)
            if drawn is not None and drawn!=current:
                self._maintenance_selection=0
                self.Draw_Maintenance_Menu();self.lcd.update();return
            selection=min(self._maintenance_selection,len(choices)-1)
            self._maintenance_dispatch(choices[selection])

    def _poll_maintenance_ui(self):
        self._maintenance_init()
        owner=getattr(self.pd,'maintenance_pulse',None)
        reader=getattr(self.pd,'maintenance_reader',None)
        visible=self.checkkey==self.MaintenanceMenu
        active_page=self._maintenance_page
        if (visible and active_page in ('root','service','service_task')
                and self._maintenance_records_ready and not self._maintenance_records_failed
                and not getattr(owner,'pending',False) and not getattr(reader,'pending',False)
                and monotonic()>=self._maintenance_records_refresh_at):
            self._maintenance_prefetch_records()
        sensor_future=self._maintenance_sensor_future
        if sensor_future is not None and sensor_future.done():
            self._maintenance_sensor_future=None
            try:
                reading=sensor_future.result()
                if self._maintenance_sensor_identity!=self._maintenance_identity():
                    raise ValueError('sensor_read_stale')
                if visible and active_page=='sensor_wait':
                    self._maintenance_context=reading
                    self._maintenance_show('sensor_report')
            except Exception:
                if visible and active_page=='sensor_wait':
                    self._maintenance_context=('Sensor read unavailable',
                        ('Connection, configuration or status changed.','Return to the sensor list and retry.'))
                    self._maintenance_show('notice')
        reference=self._maintenance_reference_future
        if reference is not None and reference.done():
            self._maintenance_reference_future=None
            try:
                answer=reference.result()
                if not self.pd.accept_maintenance_reference(answer):
                    raise ValueError('reference_measurement_stale')
                notice=(answer.heading,answer.lines)
            except Exception:
                notice=('Reference unavailable',('Conditions, session or storage changed.',
                    'No successful comparison is assumed.'))
            if visible and active_page=='reference_wait':
                self._maintenance_context=notice
                self._maintenance_show('notice')
        book=getattr(self.pd,'maintenance_book',None)
        poll_records=getattr(book,'poll_records',None)
        if callable(poll_records): poll_records()
        errors=self._maintenance_storage_errors()
        if errors!=self._maintenance_record_errors:
            self._maintenance_record_errors=errors
            if visible and active_page in ('root','result'):
                self.Draw_Maintenance_Menu();self.lcd.update()
        future=self._maintenance_records_future
        if future is not None and future.done():
            self._maintenance_records_future=None
            try:
                self._maintenance_records_data=future.result()
                self._maintenance_records_identity=self._maintenance_records_request_identity
                self._maintenance_records_ready=self._maintenance_records_identity==self._maintenance_identity()
                self._maintenance_records_refresh_at=monotonic()+60.
                target=self._maintenance_records_return
            except Exception:
                target='notice'
                if not self._maintenance_records_background:
                    self._maintenance_context=('Record operation failed',('Review storage and retry explicitly.','No success is assumed.'))
            background=self._maintenance_records_background
            self._maintenance_records_background=False
            self._maintenance_records_failed=target=='notice'
            if background:
                if target=='notice': self._maintenance_notice='Care records unavailable: retry in Care schedule'
                if visible and active_page=='service_task' and target!='notice':
                    policy=self._maintenance_context[0]
                    fresh=next((row for row in self._maintenance_records_data[0] if row[0]==policy),None)
                    if fresh is not None: self._maintenance_context=fresh
                if visible and active_page in ('root','service','service_task'):
                    self.Draw_Maintenance_Menu();self.lcd.update()
            elif visible and active_page=='storage':
                if target!='notice':
                    self._maintenance_context=None
                    if target=='service': self._maintenance_history=[('root',1,None)]
                    # Storage is replaced in place; its saved parent is still
                    # the history menu that Back must return to.
                self._maintenance_show(target)
        if not getattr(self, '_maintenance_advanced_this_tick', False):
            self._advance_maintenance_operations()
        result = getattr(self, '_maintenance_pending_result', None)
        if result is not None and visible:
            self._maintenance_pending_result = None
            self._maintenance_complete(result)
        elif visible and active_page == 'pulse' and getattr(owner, 'pending', False):
            self.Draw_Maintenance_Menu(); self.lcd.update()

    def _advance_maintenance_operations(self):
        """Advance controllers even when a UI overlay or UART loss hides them."""
        owner = getattr(self.pd, 'maintenance_pulse', None)
        reader = getattr(self.pd, 'maintenance_reader', None)
        result = None
        if getattr(owner, 'pending', False) is True:
            before = owner.phase
            result = self.pd.poll_maintenance_physical()
            if owner.phase != before:
                self._maintenance_selection = 0
        elif getattr(reader, 'pending', False) is True:
            result = self.pd.poll_maintenance_read()
        if result is not None:
            self._maintenance_result = self._maintenance_pending_result = result
        if (getattr(owner, 'pending', False) is True or
                getattr(reader, 'pending', False) is True) and hasattr(self, '_loop'):
            self._loop.set_interval(.1)
