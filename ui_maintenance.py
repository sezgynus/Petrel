"""Purpose-led Graphite Maintenance UI for the 272x480 encoder-only panel.

Presentation is separate from the trusted controllers. Only an explicit action
advances a workflow; observations have no timeout. No I/O in drawing/navigation.
"""
from types import SimpleNamespace
from time import monotonic, strftime, localtime
import textwrap
from maintenance_experience import (Choice, Screen, grouped, label, device_name,
                                    preparation, result_summary, result_details)
from graphite_theme import show_icon
from lcd_resources import ICON_LIBRARY_ID, ICON_MAINTENANCE_CHECK


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
            self._maintenance_records_return='service'

    def Enter_Maintenance_Menu(self):
        self._maintenance_init()
        self.checkkey=self.MaintenanceMenu
        self._maintenance_history=[]
        self._maintenance_context=None
        self._maintenance_frame=None
        self._maintenance_regions={}
        self._maintenance_show('root')

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
            return Screen('Maintenance','Care for your printer',('Choose a guided check.',),(
                Choice('Back','home'),Choice('Check printer','open','groups'),
                Choice('Findings','findings'),Choice('Service plan','service'),
                Choice('More','open','more')),'home')
        if page in ('groups','calibrations','diagnostics','targets'):
            physical,reads=self._maintenance_options()
            if page=='targets':
                calibration,topic=context
                groups=grouped(physical,calibration)
                rows=next((rows for key,title,rows in groups if key==topic),())
                title=next((title for key,title,rows in groups if key==topic),'Checks')
                choices=tuple(Choice(label(r),'prepare',r,device_name(r.device)) for r in rows)
            elif page=='diagnostics':
                title='System information'
                choices=tuple(Choice(label(r),'read',r,device_name(getattr(r,'device',None))) for r in reads)
            else:
                calibration=page=='calibrations'
                title='Calibrations' if calibration else 'Check printer'
                choices=tuple(Choice(title,'targets',(calibration,key),str(len(rows))+' available checks')
                              for key,title,rows in grouped(physical,calibration))
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
            return self._maintenance_pulse_screen()
        if page=='reading':
            return Screen('Reading information','Waiting for evidence',('The read runs in the background.',),
                          (Choice('Cancel read','cancel_read'),))
        if page=='result':
            outcome=getattr(self,'_maintenance_result',None)
            heading,lines,tone=result_summary(outcome)
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
            return Screen('Check result',heading,lines,tuple(choices),tone=tone)
        if page=='details':
            lines=[]
            for text in result_details(context):
                lines.extend(textwrap.wrap(text,30) or [''])
            return Screen('Evidence details',choices=(back,)+tuple(Choice(t,'none') for t in lines),kind='list')
        if page=='findings':
            report=self.pd.maintenance_assessment_details()
            findings=tuple(f for f in report.findings+report.trends if f.state in ('attention','issue'))
            if not findings:
                return Screen('Findings','No current alerts recorded',('This does not prove all hardware','is healthy. Start a check to','collect current evidence.'),
                              (back,Choice('Check printer','open','groups')))
            return Screen('Findings',choices=(back,)+tuple(Choice(device_name(f.device),'finding',f,
                'Needs review' if f.state=='attention' else 'Issue reported') for f in findings),kind='list')
        if page=='finding':
            from maintenance_assessment_messages import message_text
            finding=context
            try: explanation=message_text(finding.message_key)
            except KeyError: explanation='Review the recorded evidence.'
            choices=[back,Choice('Check printer','open','groups')]
            for feature in finding.actions:
                physical,_=self._maintenance_options()
                row=next((r for r in physical if r.feature_id==feature and r.device==finding.device),None)
                if row is not None: choices.append(Choice(label(row),'prepare',row))
            return Screen('Finding',device_name(finding.device),tuple(textwrap.wrap(explanation,30)),tuple(choices),tone='attention')
        if page.startswith('service'):
            return self._maintenance_service_screen()
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

    def _maintenance_service_screen(self):
        from maintenance_ui_records import TASKS
        from maintenance_assessment_store import ServicePolicy
        page=self._maintenance_page
        back=Choice('Back','back')
        if page=='service':
            if not self._maintenance_records_ready:
                return Screen('Service plan','No interval assumed',('Load your saved reminders.','Intervals require an explicit','manufacturer or user policy.'),
                    (back,Choice('Load service tasks','load_services')))
            tasks=self._maintenance_records_data[0]
            choices=[back,Choice('Add calendar reminder','service_add')]
            for policy,last,due in tasks:
                detail={'due':'Service is due','not_due':'Within your interval','unknown':'No reliable service date'}[due]
                choices.append(Choice(TASKS.get(policy.task_id,policy.task_id),'service_task',(policy,last,due),device_name(policy.device)+' / '+detail))
            if not tasks:
                return Screen('Service plan','No reminders configured',('Choose the device and task.','No interval or last-service date','will be invented.'),tuple(choices))
            return Screen('Service plan',choices=tuple(choices),kind='list')
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
        if page=='service_interval':
            device,task,days=self._maintenance_context
            return Screen('Choose your interval',str(days)+' calendar days',('Turn to change the interval.','Use your maintenance guidance.','This is a reminder, not wear','measurement.'),
                (Choice('Review reminder','service_review'),))
        if page=='service_review':
            policy=self._maintenance_context
            return Screen('Confirm reminder',TASKS.get(policy.task_id,policy.task_id),
                (device_name(policy.device),'Every %d calendar days' % (policy.interval/86400),
                 'Source: user-defined interval.','No service is marked completed.'),
                (back,Choice('Save reminder','service_save',policy),Choice('Discard reminder','service_discard')))
        if page=='service_task':
            policy,last,due=self._maintenance_context
            date=strftime('%Y-%m-%d',localtime(last['timestamp'])) if last and type(last.get('timestamp')) in (int,float) else 'Not recorded'
            return Screen('Service reminder',TASKS.get(policy.task_id,policy.task_id),
                (device_name(policy.device),'Last service: '+date,
                 {'due':'Your interval has elapsed.','not_due':'Within the configured interval.','unknown':'Due date cannot be determined.'}[due],
                 'Follow manufacturer guidance.'),
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
        choices=screen.choices
        self._maintenance_selection=max(0,min(self._maintenance_selection,max(0,len(choices)-1)))
        selection=self._maintenance_selection
        page=self._maintenance_page
        frame=(id(self.lcd),page,screen.kind,screen.title,len(choices))
        if frame!=self._maintenance_frame:
            self._maintenance_frame=frame
            self._maintenance_regions={}
            self._maintenance_scroll=0
            self._list_render=None
            self.lcd.draw_rectangle(1,0x2125,0,0,271,359)
            self.Draw_Title(screen.title)
        self._maintenance_drawn_choices=tuple((c.action,c.value) for c in choices)
        if screen.kind=='home':
            self._maintenance_button('back',choices[0],8,37,256,30,selection==0)
            self._maintenance_text('hero',screen.heading,17,83,30)
            self._maintenance_text('hero_sub','Capability-based checks',17,106,39,True,color=0x9CD3)
            for i in range(4):
                x=17 if i%2==0 else 145
                y=130 if i<2 else 246
                active=selection==i+1
                sig=(active,choices[i+1].label)
                if self._maintenance_regions.get(('tile',i))!=sig:
                    self._maintenance_regions[('tile',i)]=sig
                    # Managed text-free Graphite tiles, matching Petrel's home.
                    show_icon(self.lcd,ICON_LIBRARY_ID,ICON_MAINTENANCE_CHECK+i*2+int(active),x,y)
                    label_text=choices[i+1].label
                    self.lcd.draw_text(False,False,self.lcd.font8x16,0xE75E,0x19E9 if active else 0x2967,
                        x+max(2,(110-8*len(label_text))//2),y+78,label_text)
        elif screen.kind=='list':
            start=getattr(self,'_maintenance_scroll',0)
            start=max(0,min(start,selection),selection-5)
            if start!=getattr(self,'_maintenance_scroll',0):
                self._maintenance_regions={}
                self.lcd.draw_rectangle(1,0x2125,0,31,271,359)
            self._maintenance_scroll=start
            for i,choice in enumerate(choices[start:start+6]):
                self._maintenance_button(('row',i),choice,8,37+i*52,250,48,selection==start+i,bool(choice.detail))
            if len(choices)>6:
                self.lcd.draw_rectangle(1,0x39C8,265,37,267,346)
                h=max(10,310*6//len(choices));y=37+(310-h)*start//(len(choices)-6)
                self.lcd.draw_rectangle(1,0x063B,265,y,267,y+h-1)
        else:
            for i,part in enumerate((textwrap.wrap(screen.heading,30)+['',''])[:2]):
                self._maintenance_text(('heading',i),part,12,45+i*18,31,color=0xFF0F if screen.tone in ('attention','danger') else 0xE75E)
            lines=[]
            for text in screen.lines:
                lines.extend(textwrap.wrap(str(text),30) or [''])
            notice=getattr(self,'_maintenance_notice','')
            if notice:
                lines=(textwrap.wrap(notice.replace('_',' '),30)[:2])+lines[:5]
            # The long version is available under Details; never paint into actions.
            for i in range(7):
                text=lines[i] if i<len(lines) else ''
                self._maintenance_text(('line',i),text,12,81+i*18,31,True,color=0x9CD3)
            visible=3
            start=max(0,min(getattr(self,'_maintenance_scroll',0),selection),selection-visible+1)
            if start!=getattr(self,'_maintenance_scroll',0):
                self._maintenance_regions={k:v for k,v in self._maintenance_regions.items() if not isinstance(k,tuple) or k[0]!='action'}
                self.lcd.draw_rectangle(1,0x2125,8,229,267,357)
            self._maintenance_scroll=start
            for i in range(visible):
                if start+i<len(choices):
                    self._maintenance_button(('action',i),choices[start+i],8,231+i*41,256,37,selection==start+i)
            if len(choices)>visible:
                self._maintenance_text('choices_count','%d/%d' % (selection+1,len(choices)),218,209,8,True)
        owner=getattr(self.pd,'maintenance_pulse',None)
        color=getattr(owner,'display_color',None) if page=='pulse' else None
        # Diagnostic colour patch stays below instruction text and above buttons.
        color_sig=(color,page)
        previous_color=self._maintenance_regions.get('color',(None,None))[0]
        if self._maintenance_regions.get('color')!=color_sig:
            self._maintenance_regions['color']=color_sig
            if color is not None or previous_color is not None:
                self.lcd.draw_rectangle(1,color if color is not None else 0x2125,16,199,255,222)
        self._trace_maintenance_ui('draw',title=screen.title,entries=tuple((c.label,) for c in choices))

    def _maintenance_complete(self,result):
        if result is None:
            return
        self._maintenance_result=result
        self._maintenance_notice=''
        self._maintenance_show('result')

    def _maintenance_dispatch(self,choice):
        action,value=choice.action,choice.value
        if action=='none': return
        if action=='historical_result':
            record=value
            outcome=SimpleNamespace(feature_id=record.get('feature'),device=record.get('device'),
                status=record.get('status'),reason='Historical record: '+str(record.get('reason','')),
                evidence=tuple(record.get('evidence',())),restore_verified=record.get('restore_verified'))
            return self._maintenance_open('details',outcome)
        if action=='service_discard':
            self._maintenance_history=[('root',3,None)]
            self._maintenance_context=None
            return self._maintenance_show('service')
        if action=='service_add': return self._maintenance_open('service_devices')
        if action=='service_device': return self._maintenance_open('service_kind',value)
        if action=='service_kind': return self._maintenance_open('service_interval',(value[0],value[1],30))
        if action=='service_review':
            from maintenance_assessment_store import ServicePolicy
            device,task,days=self._maintenance_context
            return self._maintenance_open('service_review',ServicePolicy(task,device,'calendar_s',days*86400,'user-defined interval'))
        if action=='service_task': return self._maintenance_open('service_task',value)
        if action=='service_confirm': return self._maintenance_open('service_confirm',value)
        if action in ('service_save','service_complete'):
            return self._maintenance_load_records('save_policy' if action=='service_save' else 'complete',value)
        if action=='load_history': return self._maintenance_load_records(history=True)
        if action=='home': return self._maintenance_back_home()
        if action=='back': return self._maintenance_back()
        if action=='open': return self._maintenance_open(value)
        if action=='targets': return self._maintenance_open('targets',value)
        if action=='prepare': return self._maintenance_open('prepare',value)
        if action=='details': return self._maintenance_open('details',value)
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
            elif result is not None: self._maintenance_complete(result)
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
        self._maintenance_records_return='history_records' if history else 'service'
        # A write is already explicitly authorized. Leaving this wait view does
        # not replay or duplicate it; its Future remains owned until completion.
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
            device,task,days=self._maintenance_context
            steps=max(1,int(getattr(self,'_menu_batch_steps',1)))
            days=max(1,min(3650,days+(steps if event==self.ENCODER_DIFF_CW else -steps)))
            self._maintenance_context=(device,task,days)
            self.Draw_Maintenance_Menu();self.lcd.update();return
        choices=self._maintenance_screen().choices
        if event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            steps=max(1,int(getattr(self,'_menu_batch_steps',1)))
            delta=steps if event==self.ENCODER_DIFF_CW else -steps
            self._maintenance_selection=max(0,min(max(0,len(choices)-1),self._maintenance_selection+delta))
            self.Draw_Maintenance_Menu();self.lcd.update()
        elif event==self.ENCODER_DIFF_ENTER and choices:
            selection=min(self._maintenance_selection,len(choices)-1)
            self._maintenance_dispatch(choices[selection])

    def _poll_maintenance_ui(self):
        self._maintenance_init()
        owner=getattr(self.pd,'maintenance_pulse',None)
        reader=getattr(self.pd,'maintenance_reader',None)
        visible=self.checkkey==self.MaintenanceMenu
        active_page=self._maintenance_page
        future=self._maintenance_records_future
        if future is not None and future.done():
            self._maintenance_records_future=None
            try:
                self._maintenance_records_data=future.result()
                self._maintenance_records_ready=True
                target=self._maintenance_records_return
            except Exception:
                target='notice'
                self._maintenance_context=('Record operation failed',('Review storage and retry explicitly.','No success is assumed.'))
            if visible and active_page=='storage':
                if target!='notice':
                    self._maintenance_context=None
                    if target=='service': self._maintenance_history=[('root',3,None)]
                    elif self._maintenance_history: self._maintenance_history.pop()
                self._maintenance_show(target)
        if getattr(owner,'pending',False):
            result=self.pd.poll_maintenance_physical()
            if result is not None:
                self._maintenance_result=result
                if visible: self._maintenance_complete(result)
            elif visible and active_page=='pulse':
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
