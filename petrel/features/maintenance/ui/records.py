"""Maintenance care, service/history presentation and record I/O requests."""
from time import monotonic, strftime, localtime, time
from petrel.features.maintenance.ui.experience import Choice, Screen, device_name
from petrel.features.maintenance.ui.care import care_items
from petrel.features.maintenance.records.care import tasks as care_tasks, task_label
from petrel.features.maintenance.ui.icons import icon_for


class MaintenanceRecordsMixin:
    def _maintenance_prefetch_records(self):
        if self._maintenance_records_future is not None:
            return
        same_identity=self._maintenance_records_identity==self._maintenance_identity()
        if self._maintenance_records_ready and same_identity and monotonic()<self._maintenance_records_refresh_at:
            return
        if not same_identity: self._maintenance_records_ready=False
        self._maintenance_records_refresh_at=monotonic()+60.
        try:
            self._maintenance_records_future=self.pd.maintenance_ui_records('load',policy=None,history=False)
            self._maintenance_records_request_identity=self._maintenance_identity()
            self._maintenance_records_background=True
            self._maintenance_records_failed=False
        except Exception:
            self._maintenance_records_failed=True
        self.Draw_Maintenance_Menu();self.lcd.update()

    def _maintenance_care(self):
        if not self._maintenance_records_ready or self._maintenance_records_identity!=self._maintenance_identity():
            return ()
        if not self._maintenance_records_data[0]: return ()
        physical,reads=self._maintenance_options()
        devices=set(self._maintenance_devices())
        return care_items(self._maintenance_records_data[0],devices,time())

    def _maintenance_storage_errors(self):
        errors=getattr(getattr(self.pd,'maintenance_book',None),'errors',0)
        return errors if type(errors) is int and errors>0 else 0

    def _maintenance_identity(self):
        snapshot=getattr(getattr(self.pd,'maintenance',None),'snapshot',None)
        return (getattr(snapshot,'epoch',None),getattr(snapshot,'config_marker',None))

    def _maintenance_policy_due(self,policy,last,cached):
        from petrel.features.maintenance.assessment.store import service_due
        return (service_due(policy,now=time(),
                last_at=last.get('timestamp',last.get('_tracking_started_at')) if last else None)
                if policy.basis=='calendar_s' else cached)

    def _maintenance_service_due_count(self):
        if not self._maintenance_records_ready or self._maintenance_records_identity!=self._maintenance_identity():
            return 0
        snapshot=getattr(getattr(self.pd,'maintenance',None),'snapshot',None)
        devices=set(self._maintenance_devices())
        return sum(1 for policy,last,cached in self._maintenance_records_data[0]
                   if policy.device in devices and self._maintenance_policy_due(policy,last,cached)=='due')

    def _maintenance_service_screen(self):
        from petrel.features.maintenance.records.ui_requests import TASKS
        from petrel.features.maintenance.assessment.store import ServicePolicy, service_due
        page=self._maintenance_page
        back=Choice('Back','back')
        if page=='service':
            if self._maintenance_records_identity!=self._maintenance_identity():
                self._maintenance_records_ready=False
            if not self._maintenance_records_ready:
                loading=self._maintenance_records_future is not None
                return Screen('Care schedule','Loading care records' if loading else 'No interval assumed',
                    ('Saved policies load in the background.' if loading else 'Load or retry your saved reminders.',
                     'No service date is invented.'),
                    (back,) if loading else (back,Choice('Load care plans','load_services')))
            items=self._maintenance_care()
            choices=(back,)+tuple(Choice(item.label,'service_task',(item.policy,item.last,item.state),
                {'due':'Service is due','not_due':'Within your interval','unknown':item.detail}[item.state]) for item in items)+(
                Choice('Add reminder','service_add'),Choice('Refresh records','load_services'))
            return Screen('Care schedule',choices=choices,kind='care',care=items)
        if page=='service_devices':
            physical,reads=self._maintenance_options()
            devices=self._maintenance_devices()
            # Prefer the existing axis entry over an additional travel-only
            # alias. Keep that alias available when no axis entry was found.
            devices=tuple(d for d in devices if not (d in ('axis_x','axis_y','axis_z')
                          and 'stepper_'+d[-1] in devices))
            omitted=getattr(self.pd.maintenance.snapshot,'care_omitted',0)
            return Screen('Choose device',heading=(str(omitted)+' devices beyond capacity') if omitted else '',
                choices=(back,)+tuple(Choice(device_name(d),'service_device',d) for d in devices),kind='list')
        if page=='service_kind':
            device=self._maintenance_context
            return Screen('Choose maintenance class',choices=(back,)+tuple(
                Choice(task_label(k,device),'service_kind',(device,k)) for k in care_tasks(device)),kind='list')
        if page=='service_basis':
            device,task=self._maintenance_context
            provider=getattr(self.pd,'maintenance_service_bases',None)
            bases=provider(device) if callable(provider) else ('calendar_s',)
            if not isinstance(bases,(tuple,list)): bases=('calendar_s',)
            names={'calendar_s':'Calendar days','sampled_print_s':'Sampled printing hours',
                   'sampled_on_s':'Sampled powered hours','travel_mm':'Recorded travel (metres)',
                   'observed_trigger_count':'Legacy sampled activations',
                   'trigger_count':'Recorded sensor events',
                   'filament_mm':'Extruded filament (metres)'}
            return Screen('Choose reminder basis',task_label(task,device),choices=(back,)+tuple(
                Choice(names[b],'service_basis',(device,task,b)) for b in bases if b in names),kind='list')
        if page=='service_interval':
            device,task,amount=self._maintenance_context[:3]
            basis=self._maintenance_context[3] if len(self._maintenance_context)>3 else 'calendar_s'
            return Screen('Choose your interval',str(amount)+(' calendar days' if basis=='calendar_s' else
                ' metres travelled' if basis=='travel_mm' else
                ' metres extruded' if basis=='filament_mm' else
                ' recorded events' if basis in ('observed_trigger_count','trigger_count') else ' sampled hours'),
                ('Use your maintenance guidance.',),
                (Choice('Review reminder','service_review'),))
        if page=='service_review':
            policy=self._maintenance_context
            return Screen('Confirm reminder',task_label(policy.task_id,policy.device),
                (device_name(policy.device),('Every %d calendar days' % (policy.interval/86400)) if policy.basis=='calendar_s'
                 else ('After %d metres travelled' % (policy.interval/1000)) if policy.basis=='travel_mm'
                 else ('After %d metres extruded' % (policy.interval/1000)) if policy.basis=='filament_mm'
                 else ('After %d recorded events' % policy.interval) if policy.basis in ('observed_trigger_count','trigger_count')
                 else ('After %d sampled hours' % (policy.interval/3600)),
                 'Source: user-defined interval.','No service is marked completed.'),
                (back,Choice('Save reminder','service_save',policy),Choice('Discard reminder','service_discard')))
        if page=='service_task':
            policy,last,due=self._maintenance_context
            physical,reads=self._maintenance_options()
            if policy.device not in self._maintenance_devices():
                return Screen('Service reminder','Tracking paused' if policy.basis=='travel_mm' else 'Device no longer available',
                    ('Enable axis travel in configure.sh.' if policy.basis=='travel_mm' else 'Refresh the service plan.',),
                    (back,Choice('Remove reminder','service_remove_confirm',policy)))
            due=self._maintenance_policy_due(policy,last,due)
            stamp=last.get('timestamp') if last else None
            date=strftime('%Y-%m-%d',localtime(stamp)) if type(stamp) in (int,float) and 0<=stamp<=32503680000 else 'Not recorded'
            coverage=() if policy.basis=='calendar_s' else (
                'Counts cover enabled recording.' if policy.basis in ('observed_trigger_count','trigger_count') else
                'Recorded travel is a lower bound.' if policy.basis=='travel_mm' else
                'Moonraker history counts print jobs only.' if policy.basis=='filament_mm' else 'Sampled time is a lower bound.',
                'Below limit does not prove not due.')
            return Screen('Service reminder',task_label(policy.task_id,policy.device),
                (device_name(policy.device),'Last service: '+date,
                 {'due':'Your interval has elapsed.','not_due':'Within the configured interval.','unknown':care_items(((policy,last,due),),{policy.device},time())[0].detail}[due],
                 'Follow manufacturer guidance.')+coverage,
                (back,Choice('I completed this service','service_confirm',policy),
                 Choice('Remove reminder','service_remove_confirm',policy)),tone='attention' if due=='due' else 'normal')
        if page=='service_remove_confirm':
            policy=self._maintenance_context
            return Screen('Remove reminder?',task_label(policy.task_id,policy.device),
                (device_name(policy.device),'Removes this reminder only.',
                 'Usage and service history stay.'),
                (Choice('Keep reminder','back'),Choice('Remove reminder','service_remove',policy)),
                tone='attention')
        if page=='service_confirm':
            return Screen('Confirm completed service','Did you finish the work?',('Only confirm actual maintenance.','This writes a service date,','not a hardware test result.'),
                (back,Choice('Yes, record completion','service_complete',self._maintenance_context)))
        return Screen('Service plan',choices=(back,))

    def _maintenance_history_screen(self):
        return Screen('Usage and history','Records, not lifetime counters',('Print history covers recorded jobs.','Sampled ON time is a lower bound.','Open the records you need.'),(
            Choice('Back','back'),Choice('Recent check history','load_history'),
            Choice('Recorded print usage','history_read','S10'),Choice('Sampled component usage','history_read','S12')))

    def _maintenance_rows(self):
        screen=self._maintenance_screen()
        return screen.title,tuple((c.label,icon_for(c),None,None) for c in screen.choices)

    def _maintenance_load_records(self,operation='load',policy=None,history=False):
        if self._maintenance_records_future is not None:
            return
        try:
            future=self.pd.maintenance_ui_records(operation,policy=policy,history=history)
        except Exception:
            return self._maintenance_open('notice',('Records unavailable',('The request could not be queued.','No maintenance was recorded.')))
        self._maintenance_records_future=future
        self._maintenance_records_request_identity=self._maintenance_identity()
        self._maintenance_records_return='history_records' if history else 'service'
        # A write is already explicitly authorized. Leaving this wait view does
        # not replay or duplicate it; its Future remains owned until completion.
        self._maintenance_records_background=False
        self._maintenance_open('storage')

    def _maintenance_storage_action(self,action,value):
        if action=='load_services': return self._maintenance_load_records()
        feature='S20' if action=='export' else value
        row=next((r for r in self.pd.maintenance_read_plan() if r.feature_id==feature),None)
        if row is not None:
            return self._maintenance_dispatch(Choice('Read records','read',row))
        self._maintenance_open('notice',('No data source available',('This information is not supported','by the current installation.')))
