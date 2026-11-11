"""Maintenance screen models and display rendering."""
from time import strftime, localtime
import textwrap
from petrel.features.maintenance.ui.experience import Choice, Screen, grouped, label, device_name, preparation, result_summary, LABELS
from petrel.features.maintenance.ui.evidence import outcome_text
from petrel.features.maintenance.ui.layout import draw_maintenance
from petrel.features.maintenance.ui.icons import feature_icon
from petrel.features.maintenance.ui.report import ReportSection, section_from_lines, cached_report_rows, report_navigation
from petrel.artwork.resources import ICON_MAINTENANCE_CHECK, ICON_MAINTENANCE_RECOMMENDATIONS, ICON_MAINTENANCE_DIAGNOSTICS


class MaintenanceScreensMixin:
    def _maintenance_options(self):
        physical=tuple(self.pd.maintenance_guided_plan())
        reads=tuple(self.pd.maintenance_read_plan())
        return physical,reads

    def _maintenance_devices(self):
        physical,reads=self._maintenance_options()
        devices=tuple(dict.fromkeys(r.device for r in physical+reads if getattr(r,'device',None)))
        provider=getattr(self.pd,'maintenance_service_devices',None)
        extra=provider() if callable(provider) else ()
        return tuple(dict.fromkeys(devices+tuple(extra)))

    def _maintenance_screen(self):
        screen=self._maintenance_screen_model()
        if screen.kind=='detail' and screen.lines:
            pinned=bool(screen.choices and screen.choices[0].action in ('back','home','result_back'))
            count=sum(max(1,len(textwrap.wrap(str(line),39))) for line in screen.lines)
            if (count>(5 if pinned else 7) or len(textwrap.wrap(screen.heading,30))>2) and not any(
                    c.action=='instructions' for c in screen.choices):
                from dataclasses import replace
                screen=replace(screen,choices=screen.choices+(Choice('Read full instructions','instructions',
                    (screen.heading,)+screen.lines),))
        if screen.kind=='report':
            from dataclasses import replace
            rows=cached_report_rows(self,screen)
            position,offset,selected,_=report_navigation(rows,screen.choices,self._maintenance_report_position)
            self._maintenance_report_position=position
            self._maintenance_selection=selected
            screen=replace(screen,report_offset=offset)
        return screen

    def _maintenance_screen_model(self):
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
                Choice('Sensors','open','sensor_devices'),
                Choice('Usage and history','history'),Choice('Support tools','open','support')),kind='list')
        if page=='sensor_devices':
            provider=getattr(self.pd,'maintenance_sensor_devices',None)
            names=provider() if callable(provider) else ()
            return Screen('Sensor diagnostics',choices=(back,)+tuple(
                Choice(device_name(d),'sensor_read',d,d) for d in names),kind='list',
                heading='' if names else 'No configured sensors')
        if page=='sensor_wait':
            return Screen('Sensor diagnostics','Reading status',
                ('This read does not move the printer.',),(back,))
        if page=='sensor_report':
            reading=context
            return Screen('Sensor diagnostics',device_name(reading.device),
                choices=(back,Choice('Refresh reading','sensor_refresh',reading.device)),
                kind='report',badge='STATUS SNAPSHOT',report_icon=ICON_MAINTENANCE_DIAGNOSTICS,
                sections=(ReportSection('Source',facts=(
                    ('Configured','Yes' if reading.configured else 'No'),
                    ('Status object','Present' if reading.listed else 'Not exposed'),
                    ('Source',reading.source))),
                    ReportSection('Readings',facts=reading.facts),
                    ReportSection('Reading meaning',text=reading.notes)))
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
            if getattr(outcome,'status','') is None and getattr(outcome,'evidence',()):
                from petrel.features.maintenance.ui.evidence import evidence_lines
                facts=evidence_lines(getattr(outcome,'feature_id',''),outcome.evidence)
                return Screen('Diagnostic data',LABELS.get(getattr(outcome,'feature_id',''),'Recorded information'),
                    choices=(Choice('Back','result_back'),),kind='report',badge='INFORMATION',
                    report_icon=feature_icon(getattr(outcome,'feature_id',''),getattr(outcome,'device',None)),
                    sections=section_from_lines('',facts))
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
            from petrel.features.maintenance.assessment.reference import heating_observation
            try: heating_observation(outcome)
            except (ValueError,TypeError,AttributeError): pass
            else: choices.append(Choice('Heating speed reference','reference',outcome))
            return Screen('Check result',heading,lines=tuple(lines),choices=tuple(choices),kind='report',tone=tone,
                badge='NEEDS REVIEW' if tone in ('attention','danger') else 'RESULT',
                report_icon=ICON_MAINTENANCE_RECOMMENDATIONS if tone in ('attention','danger') else ICON_MAINTENANCE_CHECK,
                sections=(ReportSection('What this means',tuple(lines)),))
        if page=='reference':
            from petrel.features.maintenance.assessment.reference import heating_observation
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
                (),
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
            from petrel.features.maintenance.ui.evidence import evidence_lines
            sections=[]
            historical=str(getattr(context,'reason','')).startswith('Historical')
            if historical: sections.append(ReportSection(text=('Historical record; not current health.',)))
            for outcome in (getattr(context,'components',()) or (context,))[:16]:
                feature=getattr(outcome,'feature_id','')
                sections.extend(section_from_lines(LABELS.get(feature,'Recorded evidence'),
                    (outcome_text(getattr(outcome,'status',None)),)+evidence_lines(feature,getattr(outcome,'evidence',()))))
            restored=getattr(context,'restore_verified',None)
            if restored is not None:
                sections.append(ReportSection(text=('Previous state restored' if restored else 'Previous state not confirmed',)))
            return Screen('Evidence details',device_name(getattr(context,'device',None)),choices=(back,),
                kind='report',badge='HISTORY' if historical else 'MEASUREMENTS',
                report_icon=feature_icon(getattr(context,'feature_id',''),getattr(context,'device',None)),sections=tuple(sections))
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
            from petrel.features.maintenance.assessment.messages import message_text
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
            return Screen('Recommendation',device_name(findings[0].device),choices=tuple(choices),kind='report',
                tone='attention',badge='RECOMMENDATION',report_icon=ICON_MAINTENANCE_RECOMMENDATIONS,
                sections=tuple(ReportSection('What to review' if i==0 else '',(text,)) for i,text in enumerate(explanations)))
        if page=='instructions':
            return Screen('Full instructions','Read at your own pace',choices=(back,),kind='report',badge='GUIDANCE',
                report_icon=ICON_MAINTENANCE_DIAGNOSTICS,sections=(ReportSection(text=tuple(context)),))
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
                choices.append(Choice(name,'historical_result',record,date+' / '+outcome_text(record.get('status'))))
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
            return Screen('Measured value','%.2f %s' % (value,unit),(),
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

    def Draw_Maintenance_Menu(self,screen=None):
        self._maintenance_init()
        if screen is None: screen=self._maintenance_screen()
        self._maintenance_last_screen=screen
        draw_maintenance(self,screen)
        self._trace_maintenance_ui('draw',title=screen.title,entries=tuple((c.label,) for c in screen.choices))
