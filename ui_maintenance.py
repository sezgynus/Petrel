"""Purpose-led Graphite Maintenance UI for the 272x480 encoder-only panel.

Presentation is separate from the trusted controllers. Only an explicit action
advances a workflow; observations have no timeout. No I/O in drawing/navigation.
"""
from types import SimpleNamespace
from time import monotonic, strftime, localtime, time
import textwrap
from maintenance_experience import (Choice, Screen, grouped, label, device_name,
                                    preparation, result_summary, result_details)
from graphite_theme import show_icon
from maintenance_care_view import care_items
from maintenance_layout import draw_maintenance


class MaintenanceViewMixin:
    def _trace_maintenance_ui(self,kind='tick',event=None,title=None,entries=None):
        trace=getattr(self.pd,'maintenance_test_trace',None)
        if trace is not None and trace.active:
            trace.ui(self,kind,event,title,entries)

    def _maintenance_init(self):
        if not hasattr(self,'_maintenance_history'):
            self._maintenance_history=[]
            self._maintenance_page='root'
            self._maintenance_selection=0
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

    def Enter_Maintenance_Menu(self):
        self._maintenance_init()
        self.checkkey=self.MaintenanceMenu
        self._maintenance_history=[]
        self._maintenance_context=None
        self._maintenance_frame=None
        self._maintenance_regions={}
        self._maintenance_show('root')
        self._maintenance_prefetch_records()

    def _maintenance_prefetch_records(self):
        if self._maintenance_records_future is not None:
            return
        if self._maintenance_records_ready and self._maintenance_records_identity==self._maintenance_identity():
            return
        self._maintenance_records_ready=False
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
        devices={r.device for r in physical+reads}
        return care_items(self._maintenance_records_data[0],devices,time())

    def _maintenance_back_home(self):
        self._maintenance_history=[]
        self._maintenance_frame=None
        self._maintenance_page='root'
        self._maintenance_selection=0
        self.select_page.set(next(i for i,e in enumerate(self._home_entries()) if e[0]=='MAINTENANCE'))
        self.Goto_MainMenu()
        self.lcd.update()

    def _maintenance_show(self,page,selection=0):
        self._maintenance_init()
        self._maintenance_page=page
        self._maintenance_selection=selection
        self.Draw_Maintenance_Menu()
        self.lcd.update()

    def _maintenance_open(self,page,context=None):
        self._maintenance_init()
        self._maintenance_history.append((self._maintenance_page,self._maintenance_selection,self._maintenance_context))
        self._maintenance_context=context
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

    def _maintenance_options(self):
        physical=tuple(self.pd.maintenance_guided_plan())
        reads=tuple(self.pd.maintenance_read_plan())
        return physical,reads

    def _maintenance_screen(self):
        self._maintenance_init()
        page=self._maintenance_page
        context=self._maintenance_context
        back=Choice('Back','back')
        if page=='root':
            evidence=self.pd.maintenance_assessment.has_current_evidence(self.pd.maintenance.snapshot)
            report=self.pd.maintenance_assessment_details() if evidence else None
            findings=tuple(f for f in report.findings+report.trends if f.state in ('attention','issue')) if report else ()
            items=self._maintenance_care()
            heading=('Care records unavailable' if self._maintenance_records_failed else
                     ('Loading care schedule' if self._maintenance_records_future is not None else 'Load saved care plans') if not self._maintenance_records_ready else
                     'No care plans' if not items else '%d plans / %d due'%(len(items),sum(i.state=='due' for i in items)))
            return Screen('Maintenance',heading,(),(
                Choice('Back','home'),Choice('Care schedule','service'),
                Choice('Check printer','open','groups'),Choice('Diagnostics','open','diagnostic_groups'),
                Choice('Recommendations (%d)'%len(findings),'findings')),'home',care=items[:2])
        if page=='diagnostic_groups':
            _,reads=self._maintenance_options()
            groups=grouped(reads)
            return Screen('Diagnostics',choices=(back,)+tuple(
                Choice(title,'diagnostic_topic',key) for key,title,rows in groups)+(
                Choice('Usage and history','history'),Choice('Support tools','open','support')),kind='list')
        if page=='diagnostic_topic':
            _,reads=self._maintenance_options()
            groups=grouped(reads)
            rows=next((rows for key,title,rows in groups if key==context),())
            title=next((title for key,title,rows in groups if key==context),'Diagnostics')
            return Screen(title,choices=(back,)+tuple(Choice(label(r),'read',r,
                device_name(getattr(r,'device',None))) for r in rows),kind='list')
        if page in ('groups','calibrations','diagnostics','targets'):
            physical,reads=self._maintenance_options()
            if page=='targets':
                calibration,topic=context
                groups=grouped(physical,calibration)
                rows=next((rows for key,title,rows in groups if key==topic),())
                title=next((title for key,title,rows in groups if key==topic),'Checks')
                choices=tuple(Choice(label(r),'prepare',r,device_name(r.device)) for r in rows)
            elif page=='diagnostics':
                title='Diagnostics'
                choices=tuple(Choice(label(r),'read',r,device_name(getattr(r,'device',None))) for r in reads)
            else:
                calibration=page=='calibrations'
                title='Calibrations' if calibration else 'Check printer'
                choices=tuple(Choice(title,'targets',(calibration,key),str(len(rows))+' available checks')
                              for key,title,rows in grouped(physical,calibration))
            if page=='groups' and grouped(physical,True):
                choices=choices+(Choice('Calibrations','open','calibrations'),)
            if not choices:
                return Screen(title,'No supported checks',('Only installed, supported','functions are shown.'),(back,))
            return Screen(title,choices=(back,)+choices,kind='list')
        if page=='more':
            return Screen('More',choices=(back,Choice('Calibrations','open','calibrations'),
                Choice('System information','open','diagnostics'),Choice('Usage and history','history'),
                Choice('Leveling tools','leveling'),Choice('Support tools','open','support')),kind='list')
        if page=='leveling':
            return Screen('Leveling','Keep everyday tools together',('Offset, mesh and screw','adjustment stay in Leveling.','Return home to open Leveling.'),(back,))
        if page=='support':
            return Screen('Support tools','Optional diagnostic capture',('Recording does not run checks.','Exports contain bounded,','sanitized diagnostic evidence.'),(
                back,Choice(self.pd.maintenance_test_recording_label(),'trace'),Choice('Export diagnostic report','export')))
        if page=='prepare':
            row=context
            return Screen(device_name(row.device),label(row),preparation(row),(
                back,Choice('Prepare check','start',row)),tone='attention')
        if page=='pulse':
            screen=self._maintenance_pulse_screen()
            lines=tuple(part for text in screen.lines for part in textwrap.wrap(str(text),30))
            if len(lines)>7:
                from dataclasses import replace
                screen=replace(screen,choices=screen.choices+(Choice('Read full instructions','instructions',screen.lines),))
            return screen
        if page=='reading':
            return Screen('Reading information','Waiting for evidence',('The read runs in the background.',),
                          (Choice('Cancel read','cancel_read'),))
        if page=='result':
            outcome=getattr(self,'_maintenance_result',None)
            heading,lines,tone=result_summary(outcome)
            if self._maintenance_storage_errors():
                lines=tuple(lines)+('Some records could not be saved.','Review storage and history.')
            choices=[Choice('Back to checks','result_back'),Choice('Details','details',outcome)]
            # Offer only a currently registered PID flow for the same heater.
            failed=any(getattr(c,'feature_id',None) in ('H07','H08') and c.status=='FAILED_METRIC'
                       for c in getattr(outcome,'components',()))
            if failed:
                physical,_=self._maintenance_options()
                row=next((r for r in physical if r.device==getattr(outcome,'device',None)
                          and r.feature_id in ('H02','H03','H04')),None)
                if row is not None:
                    choices.append(Choice('Review PID calibration','prepare',row))
            from maintenance_reference import heating_observation
            try: heating_observation(outcome)
            except (ValueError,TypeError,AttributeError): pass
            else: choices.append(Choice('Heating speed reference','reference',outcome))
            return Screen('Check result',heading,lines,tuple(choices),tone=tone)
        if page=='reference':
            from maintenance_reference import heating_observation
            item=heating_observation(context)
            choices=[back]
            if item.status=='PASSED_USER':
                choices.append(Choice('Save as reference','reference_confirm',('save',context,None)))
            choices.extend((Choice('Compare with reference','reference_limit',context),
                Choice('Hardware changed: remove','reference_confirm',('clear',context,None))))
            return Screen('Heating speed reference',device_name(item.device),
                ('A reference is one measured response.','It does not certify hardware life.',
                 'Comparison needs the same setup.'),tuple(choices))
        if page=='reference_limit':
            outcome,percent=context
            return Screen('Choose your review limit',str(percent)+'% change',
                ('Turn to change the review limit.','This is your chosen threshold,',
                 'not a manufacturer wear limit.'),
                (Choice('Review comparison','reference_confirm',('compare',outcome,percent/100)),))
        if page=='reference_confirm':
            operation,outcome,limit=context
            lines=(('Same heater and nozzle hardware?','Same cooling setup during check?',
                    'If changed, remove the reference.','Your review limit: %.0f%%'%(limit*100))
                   if operation=='compare' else
                   ('Only use known-working hardware.','Fan start state was recorded.',
                    'Save this measured heating speed?') if operation=='save' else
                   ('Remove the old device reference.','Run a new check after replacement.'))
            return Screen('Confirm reference action',{'save':'Accept this reference?',
                'compare':'Are comparison conditions true?','clear':'Hardware or setup changed?'}[operation],
                lines,(back,Choice('Yes, continue','reference_run',context)),tone='attention')
        if page=='reference_wait':
            return Screen('Heating speed reference','Processing reference',('No hardware action is running.',),())
        if page=='details':
            lines=[]
            for text in result_details(context):
                lines.extend(textwrap.wrap(text,30) or [''])
            return Screen('Evidence details',choices=(back,)+tuple(Choice(t,'none') for t in lines),kind='list')
        if page=='findings':
            report=self.pd.maintenance_assessment_details()
            findings=tuple(f for f in report.findings+report.trends if f.state in ('attention','issue'))
            if not findings:
                return Screen('Recommendations','No current alerts recorded',('This does not prove all hardware','is healthy. Start a check to','collect current evidence.'),
                              (back,Choice('Check printer','open','groups')))
            subjects={}
            for finding in findings:
                subjects.setdefault(finding.device,[]).append(finding)
            return Screen('Recommendations',choices=(back,)+tuple(Choice(device_name(device),'finding',tuple(items),
                '%d finding%s to review' % (len(items),'s' if len(items)!=1 else ''))
                for device,items in subjects.items()),kind='list')
        if page=='finding':
            from maintenance_assessment_messages import message_text
            findings=context if isinstance(context,tuple) else (context,)
            explanations=[]
            choices=[back,Choice('Check printer','open','groups')]
            physical,_=self._maintenance_options()
            offered=set()
            for finding in findings:
                try: explanation=message_text(finding.message_key)
                except KeyError: explanation='Review the recorded evidence.'
                if explanation not in explanations: explanations.append(explanation)
                for feature in finding.actions:
                    row=next((r for r in physical if r.feature_id==feature and r.device==finding.device),None)
                    if row is not None and (feature,row.device) not in offered:
                        choices.append(Choice(label(row),'prepare',row));offered.add((feature,row.device))
            # Keep all explanations reachable rather than silently dropping text.
            lines=tuple(part for explanation in explanations for part in textwrap.wrap(explanation,30))
            if len(lines)>7:
                choices.append(Choice('Read all findings','instructions',lines))
            return Screen('Recommendation',device_name(findings[0].device),lines[:7],tuple(choices),tone='attention')
        if page=='instructions':
            lines=tuple(part for value in context for part in (textwrap.wrap(str(value),30) or ['']))
            return Screen('Full instructions',choices=(back,)+tuple(Choice(line,'none') for line in lines),kind='list')
        if page.startswith('service'):
            screen=self._maintenance_service_screen()
            if sum(max(1,len(textwrap.wrap(str(line),30))) for line in screen.lines)>7:
                from dataclasses import replace
                screen=replace(screen,choices=screen.choices+(Choice('Read full instructions','instructions',screen.lines),))
            return screen
        if page=='history':
            return self._maintenance_history_screen()
        if page=='history_records':
            records=self._maintenance_records_data[1]
            if not records:
                return Screen('Check history','No recorded checks',('Only completed recorded checks','appear here. This is not a','lifetime health history.'),(back,))
            choices=[]
            for record in records:
                name=device_name(record.get('device'))
                stamp=record.get('timestamp')
                date=strftime('%Y-%m-%d',localtime(stamp)) if type(stamp) in (int,float) and 0<=stamp<=32503680000 else 'Date unknown'
                choices.append(Choice(name,'historical_result',record,date+' / '+str(record.get('status',''))))
            return Screen('Check history',choices=(back,)+tuple(choices),kind='list')
        if page=='storage':
            return Screen('Maintenance records','Working in the background',('Please wait for the record.','No hardware action is running.'),(back,))
        if page=='notice':
            return Screen('Maintenance',str(context[0]),tuple(context[1]),(back,))
        return Screen('Maintenance',choices=(back,))

    def _maintenance_pulse_screen(self):
        owner=self.pd.maintenance_pulse
        phase=owner.phase
        feature=getattr(owner,'feature_id','') or ''
        cancel=Choice('Cancel check','cancel')
        live=tuple(str(x) for x in getattr(owner,'live_text',()))
        title='Guided check'
        if phase=='await_confirmation':
            homing=getattr(owner,'preparing_home',False)
            heading='Clear the homing path' if homing else 'Ready for your confirmation'
            if homing:
                lines=('Axes will home first.','The selected check follows.','Keep the bed and path clear.')
                start='Home axes and continue'
            else:
                lines=live or ('Only start when preparation','is complete and the area is safe.')
                start='Start check'
            if feature.startswith('H'):
                lines=lines[:2]+('Hot surfaces: keep clear.','Stop requests Klipper shutdown.')
            return Screen('Confirm check',heading,lines,(cancel,Choice(start,'confirm')),tone='attention')
        if phase in ('await_press','await_release'):
            return Screen('Sensor response',getattr(owner,'prompt','Follow the sensor instructions'),live,
                          (cancel,Choice('Read sensor now','confirm')))
        if phase=='workflow':
            choices=tuple(Choice(str(title),'choose',i) for i,(title,action) in enumerate(owner.workflow_choices))
            return Screen('Next step','Follow the physical instructions',live,(cancel,)+choices)
        if phase=='await_measurement':
            return Screen('Measure actual travel','Use a ruler or caliper',('Enter the actual distance.','The axis may still need to','return after measurement.'),
                          (cancel,Choice('Enter measurement','measure')))
        if phase=='measurement_edit':
            value=getattr(owner,'measurement_value',0.)
            unit=getattr(owner,'measurement_unit','mm')
            return Screen('Measured value','%.2f %s' % (value,unit),('Turn to adjust actual value.','Press to accept measurement.','Do not enter a guessed value.'),
                          (Choice('Accept measured value','record'),))
        if phase=='f12_await_stop':
            return Screen('Fan startup','Has the fan fully stopped?',('Wait for a physical full stop.','A zero command is not proof.'),
                          (cancel,Choice('Yes, fully stopped','fan_stop')))
        if phase=='await_observation':
            if feature=='F12':
                choices=(Choice('None started reliably','observe',0),)+tuple(
                    Choice('%d: %.1f%%' % (i+1,100*value/255),'observe',i+1)
                    for i,value in enumerate(owner.pwm_levels))+(cancel,)
                return Screen('Fan startup','First reliable starting step?',('Select the first stable rotation.','Do not guess the speed.'),choices)
            details=tuple(getattr(owner,'observation_details',()))
            prompt=getattr(owner,'observation_prompt',None) or 'Was the expected effect observed?'
            choices=[Choice('Not observed / reject','observe',False),Choice('Yes, observed / reviewed','observe',True)]
            if details:
                choices.insert(1,Choice('Review measured evidence','review',details))
            return Screen('Your observation',prompt,('Your answer has no time limit.',
                'Only confirm what you observed.'),tuple(choices))
        if phase=='stopping':
            return Screen('Stopping check','Safety stop requested',('Keep clear of the printer.','Waiting for shutdown evidence.'),(),tone='danger')
        heading={'preflight':'Checking preparation','running':'Check in progress','verifying':'Verifying completion',
                 'f12_next_preflight':'Preparing next fan step','analysis':'Analysing measured data',
                 'saving_baseline':'Saving selected reference'}.get(phase,'Waiting for controller')
        if getattr(owner,'preparing_home',False): heading='Homing before the check'
        if feature=='F12' and phase=='running':
            status=getattr(owner,'f12_status',None)
            if status:
                round_no,step,pwm,low,high=status
                live=('Round %d / step %d' % (round_no,step),'PWM %.1f%%' % (100*pwm/255),'Observe the fan starting.')
        stop='Cancel preparation' if phase=='preflight' else 'Stop: Klipper shutdown' if feature.startswith('H') else 'Stop / cancel check'
        return Screen(title,heading,live or ('Waiting for verified evidence.',),(Choice(stop,'cancel'),),tone='attention' if feature.startswith('H') else 'normal')

    def _maintenance_storage_errors(self):
        errors=getattr(getattr(self.pd,'maintenance_book',None),'errors',0)
        return errors if type(errors) is int and errors>0 else 0

    def _maintenance_identity(self):
        snapshot=getattr(getattr(self.pd,'maintenance',None),'snapshot',None)
        return (getattr(snapshot,'epoch',None),getattr(snapshot,'config_marker',None))

    def _maintenance_policy_due(self,policy,last,cached):
        from maintenance_assessment_store import service_due
        return (service_due(policy,now=time(),last_at=last.get('timestamp') if last else None)
                if policy.basis=='calendar_s' else cached)

    def _maintenance_service_due_count(self):
        if not self._maintenance_records_ready or self._maintenance_records_identity!=self._maintenance_identity():
            return 0
        snapshot=getattr(getattr(self.pd,'maintenance',None),'snapshot',None)
        devices={d.name for d in getattr(snapshot,'devices',())}
        return sum(1 for policy,last,cached in self._maintenance_records_data[0]
                   if policy.device in devices and self._maintenance_policy_due(policy,last,cached)=='due')

    def _maintenance_service_screen(self):
        from maintenance_ui_records import TASKS
        from maintenance_assessment_store import ServicePolicy, service_due
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
                {'due':'Service is due','not_due':'Within your interval','unknown':'Service date or coverage unknown'}[item.state]) for item in items)+(
                Choice('Add reminder','service_add'),Choice('Refresh records','load_services'))
            return Screen('Care schedule',choices=choices,kind='care',care=items)
        if page=='service_devices':
            physical,reads=self._maintenance_options()
            devices=tuple(dict.fromkeys(r.device for r in physical+reads if getattr(r,'device',None)))
            return Screen('Choose device',choices=(back,)+tuple(Choice(device_name(d),'service_device',d) for d in devices),kind='list')
        if page=='service_kind':
            device=self._maintenance_context
            tasks=['inspect_clean']
            if device.startswith('extruder'): tasks.append('nozzle_inspect')
            if device.startswith(('stepper_','manual_stepper ')): tasks.append('lubricate')
            return Screen('Choose service task',choices=(back,)+tuple(Choice(TASKS[k],'service_kind',(device,k)) for k in tasks),kind='list')
        if page=='service_basis':
            device,task=self._maintenance_context
            provider=getattr(self.pd,'maintenance_service_bases',None)
            bases=provider(device) if callable(provider) else ('calendar_s',)
            if not isinstance(bases,(tuple,list)): bases=('calendar_s',)
            names={'calendar_s':'Calendar days','sampled_print_s':'Sampled printing hours',
                   'sampled_on_s':'Sampled powered hours'}
            return Screen('Choose reminder basis',choices=(back,)+tuple(
                Choice(names[b],'service_basis',(device,task,b)) for b in bases if b in names),kind='list')
        if page=='service_interval':
            device,task,amount=self._maintenance_context[:3]
            basis=self._maintenance_context[3] if len(self._maintenance_context)>3 else 'calendar_s'
            return Screen('Choose your interval',str(amount)+(' calendar days' if basis=='calendar_s' else ' sampled hours'),
                ('Turn to change the interval.','Use your maintenance guidance.',
                 'Sampled time is a lower bound.' if basis!='calendar_s' else 'This reminder does not measure wear.'),
                (Choice('Review reminder','service_review'),))
        if page=='service_review':
            policy=self._maintenance_context
            return Screen('Confirm reminder',TASKS.get(policy.task_id,policy.task_id),
                (device_name(policy.device),('Every %d calendar days' % (policy.interval/86400)) if policy.basis=='calendar_s'
                 else ('After %d sampled hours' % (policy.interval/3600)),
                 'Source: user-defined interval.','No service is marked completed.'),
                (back,Choice('Save reminder','service_save',policy),Choice('Discard reminder','service_discard')))
        if page=='service_task':
            policy,last,due=self._maintenance_context
            physical,reads=self._maintenance_options()
            if policy.device not in {r.device for r in physical+reads}:
                return Screen('Service reminder','Device no longer available',('Refresh the service plan.',),(back,))
            due=self._maintenance_policy_due(policy,last,due)
            stamp=last.get('timestamp') if last else None
            date=strftime('%Y-%m-%d',localtime(stamp)) if type(stamp) in (int,float) and 0<=stamp<=32503680000 else 'Not recorded'
            coverage=() if policy.basis=='calendar_s' else (
                'Sampled time is a lower bound.','Below limit does not prove not due.')
            return Screen('Service reminder',TASKS.get(policy.task_id,policy.task_id),
                (device_name(policy.device),'Last service: '+date,
                 {'due':'Your interval has elapsed.','not_due':'Within the configured interval.','unknown':'Due date cannot be determined.'}[due],
                 'Follow manufacturer guidance.')+coverage,
                (back,Choice('I completed this service','service_confirm',policy)),tone='attention' if due=='due' else 'normal')
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
        return screen.title,tuple((c.label,self.ICON_Info,None,None) for c in screen.choices)

    def _maintenance_text(self,key,value,x,y,cells=30,small=False,color=0xE75E,bg=0x2125):
        value=str(value).replace('\n',' ').replace('\r',' ')
        w,h=(6,12) if small else (8,16)
        value=value[:min(cells,(272-x)//w)]
        signature=(value,x,y,cells,small,color,bg)
        if self._maintenance_regions.get(key)==signature:
            return
        self._maintenance_regions[key]=signature
        self.lcd.draw_rectangle(1,bg,x,y,min(271,x+cells*w-1),y+h-1)
        self.lcd.draw_text(False,False,self.lcd.font6x12 if small else self.lcd.font8x16,color,bg,x,y,value)

    def _maintenance_button(self,key,choice,x,y,width,height,selected,detail=False):
        bg=0x19E9 if selected else 0x2967
        signature=(choice.label,choice.detail,selected,x,y,width,height)
        if self._maintenance_regions.get(key)==signature:
            return
        self._maintenance_regions[key]=signature
        self.lcd.draw_rectangle(1,bg,x,y,x+width-1,y+height-1)
        if selected:
            self.lcd.draw_rectangle(0,0x063B,x,y,x+width-1,y+height-1)
            self.lcd.draw_rectangle(1,0x063B,x,y,x+2,y+height-1)
        self.lcd.draw_text(False,False,self.lcd.font8x16,0xE75E,bg,x+10,y+(7 if detail else (height-16)//2),choice.label[:(width-20)//8])
        if detail and choice.detail:
            self.lcd.draw_text(False,False,self.lcd.font6x12,0x9CD3,bg,x+10,y+27,choice.detail[:(width-20)//6])

    def Draw_Maintenance_Menu(self):
        self._maintenance_init()
        screen=self._maintenance_screen()
        draw_maintenance(self,screen)
        self._trace_maintenance_ui('draw',title=screen.title,entries=tuple((c.label,) for c in screen.choices))

    def _maintenance_complete(self,result):
        if result is None:
            return
        self._maintenance_result=result
        self._maintenance_notice=''
        self._maintenance_show('result')

    def _maintenance_dispatch(self,choice):
        action,value=choice.action,choice.value
        if action=='none': return
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
        if action=='service_device': return self._maintenance_open('service_kind',value)
        if action=='service_kind': return self._maintenance_open('service_basis',value)
        if action=='service_basis': return self._maintenance_open('service_interval',(value[0],value[1],30,value[2]))
        if action=='service_review':
            from maintenance_assessment_store import ServicePolicy
            device,task,amount=self._maintenance_context[:3]
            basis=self._maintenance_context[3] if len(self._maintenance_context)>3 else 'calendar_s'
            return self._maintenance_open('service_review',ServicePolicy(task,device,basis,
                amount*(86400 if basis=='calendar_s' else 3600),'user-defined interval'))
        if action=='service_task': return self._maintenance_open('service_task',value)
        if action=='service_confirm': return self._maintenance_open('service_confirm',value)
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
            self._maintenance_notice='' if accepted else reason
            return self._maintenance_show('pulse')
        if action=='measure':
            self.pd.maintenance_pulse.begin_measurement()
            return self._maintenance_show('pulse')
        if action=='record':
            owner=self.pd.maintenance_pulse
            accepted,reason=owner.record_measurement(owner.measurement_value)
            self._maintenance_notice='' if accepted else reason
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
        choices=self._maintenance_screen().choices
        if event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            steps=max(1,int(getattr(self,'_menu_batch_steps',1)))
            delta=steps if event==self.ENCODER_DIFF_CW else -steps
            self._maintenance_selection=max(0,min(max(0,len(choices)-1),self._maintenance_selection+delta))
            self.Draw_Maintenance_Menu();self.lcd.update()
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
                if visible and active_page in ('root','service'):
                    self.Draw_Maintenance_Menu();self.lcd.update()
            elif visible and active_page=='storage':
                if target!='notice':
                    self._maintenance_context=None
                    if target=='service': self._maintenance_history=[('root',1,None)]
                    elif self._maintenance_history: self._maintenance_history.pop()
                self._maintenance_show(target)
        if getattr(owner,'pending',False):
            before=owner.phase
            result=self.pd.poll_maintenance_physical()
            if result is not None:
                self._maintenance_result=result
                if visible: self._maintenance_complete(result)
            elif visible and active_page=='pulse':
                if owner.phase!=before: self._maintenance_selection=0
                # Field-level signatures suppress unchanged packets, including
                # after prolonged user observation; no UI timeout is introduced.
                self.Draw_Maintenance_Menu();self.lcd.update()
            if hasattr(self,'_loop'): self._loop.set_interval(.1)
        elif getattr(reader,'pending',False):
            result=self.pd.poll_maintenance_read()
            if result is not None:
                self._maintenance_result=result
                if visible: self._maintenance_complete(result)
            if hasattr(self,'_loop'): self._loop.set_interval(.1)

