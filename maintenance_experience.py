"""Pure end-user Maintenance vocabulary, grouping and evidence presentation.

This model never discovers hardware, reads files, sends commands or awards PASS.
"""
from dataclasses import dataclass
from maintenance_catalog import definition_for

TOPICS = (('thermal','Heating'),('motion','Movement'),('geometry','Bed and probe'),
          ('filament','Filament path'),('cooling','Cooling'),('vibration','Vibration'),
          ('system','System and panel'),('auxiliary','Lights and outputs'))
FAMILY = dict(F='cooling',H='thermal',M='motion',P='geometry',R='vibration',E='filament',S='system',O='auxiliary')
LEVELING = frozenset(('P05','P07','P08','P11'))
THERMAL_COMPONENTS = frozenset(('H05','H06','H07','H08','H09','H13'))
LABELS = {
 'F01':'Fan rotation','F02':'Fan speed response','F12':'Fan startup threshold',
 'H01':'Heating and cooling','H02':'Tune hotend PID','H03':'Tune bed PID','H04':'Tune heater PID',
 'M01':'Endstop response','M03':'Reference the axes','M04':'Motor movement','M05':'Axis movement',
 'M06':'Measure axis travel','M07':'Motor driver status','M12':'Endstop phase calibration',
 'P01':'Probe trigger','P03':'Probe repeatability','P04':'Single probe reading',
 'R01':'Accelerometer connection','R02':'Measure axis vibration','R03':'Sensor noise',
 'R04':'Tune Input Shaper','E01':'Filament extrusion','E02':'Measure filament feed',
 'E03':'Filament presence sensor','E07':'Observe filament path',
 'S01':'Host load and memory','S02':'Host temperature','S03':'Power and throttling',
 'S10':'Recorded print usage','S15':'Encoder response','S16':'Display colours',
 'S17':'Backlight response','S18':'Audible signal','O03':'Auxiliary output',
 'O04':'LED colours','O06':'Guided servicing'}

@dataclass(frozen=True, slots=True)
class Choice:
    label: str
    action: str
    value: object = None
    detail: str = ''

@dataclass(frozen=True, slots=True)
class Screen:
    title: str
    heading: str = ''
    lines: tuple = ()
    choices: tuple = ()
    kind: str = 'detail'
    tone: str = 'normal'


def device_name(name):
    if name is None:
        return 'Printer'
    known={'extruder':'Hotend','heater_bed':'Heated bed','fan':'Part cooling fan',
           'stepper_x':'X axis','stepper_y':'Y axis','stepper_z':'Z axis'}
    if name in known:
        return known[name]
    if name.startswith('extruder') and name[8:].isdigit():
        return 'Hotend '+name[8:]
    return name.partition(' ')[2] or name.replace('_',' ')


def label(row):
    return LABELS.get(row.feature_id, definition_for(row.feature_id).title)


def grouped(rows, calibration=False):
    """Use only actual registered rows; retain every device/axis instance."""
    rows=tuple(rows)
    heaters={r.device for r in rows if r.feature_id=='H01'}
    out={}
    for row in rows:
        if not getattr(row,'visible',True) or row.feature_id in LEVELING:
            continue
        if row.feature_id in THERMAL_COMPONENTS and row.device in heaters:
            continue
        is_calibration=row.method==8 and row.feature_id!='M03'
        if is_calibration!=calibration:
            continue
        topic=FAMILY[row.feature_id[0]]
        out.setdefault(topic,[]).append(row)
    return tuple((key,title,tuple(out[key])) for key,title in TOPICS if key in out)


def preparation(row):
    domain=definition_for(row.feature_id).safety_profile
    if domain=='heater':
        return ('Printer must be idle.','Keep clear of hot surfaces.',
                'Stop during heating requests','a Klipper safety shutdown.')
    if row.method==4:
        return ('Prepare a ruler or caliper.','Clear the bed and travel path.','Enter the measured distance,','not the commanded distance.')
    if domain in ('motion','calibration'):
        return ('Clear the bed and travel path.','Axes may home before the check.',
                'Changes are not auto-saved.')
    if domain=='extrusion':
        return ('Prepare filament and heat','the active hotend beforehand.',
                'Keep hands clear of the nozzle.')
    if domain=='mmu':
        return ('Follow the MMU preparation.','Keep the filament path clear.')
    if row.feature_id in ('E03','M01','P01'):
        return ('Printer must be cold and idle.','Follow the sensor instructions.',
                'Only touch accessible parts.')
    return ('Follow the on-screen steps.','Observe the physical effect.','A command alone is not proof.')


def result_summary(result):
    status=getattr(result,'status',None)
    reason=getattr(result,'reason','')
    if 'SHUTDOWN_UNCONFIRMED' in reason:
        return ('Check printer safety now',('Shutdown was not confirmed.','Use physical power if needed.'),'danger')
    if status in ('ERROR','BLOCKED','INCONCLUSIVE','ABORTED'):
        heading={'ERROR':'Check could not finish','BLOCKED':'Preparation required',
                 'INCONCLUSIVE':'Not enough evidence','ABORTED':'Check stopped'}[status]
        hints={
            'motion_requires_cold_idle_heaters':('Turn all heater targets off.','Wait until they are cool.'),
            'cold_idle_thermal_preflight_required':('Cool heaters and set targets','to zero before retrying.'),
            'existing_or_unknown_pending_config':('Klipper has pending settings.','Review them before retrying.'),
            'preheat_active_extruder_before_test':('Preheat the active hotend','before the extrusion check.'),
            'f12_kick_start_active':('This check needs fan kick-start','disabled in the configuration.', 'Review settings externally.')}
        return heading,hints.get(reason,('No hardware health conclusion.','Open Details for the reason.')),'attention'
    children=getattr(result,'components',())
    failed=[c.feature_id for c in children if c.status=='FAILED_METRIC']
    if failed:
        lines=[]
        if 'H07' in failed: lines.append('Temperature overshoot needs review.')
        if 'H08' in failed: lines.append('Temperature variation needs review.')
        if not lines: lines.append('A measurement needs review.')
        return 'Temperature control review',tuple(lines)+('This is not a part-failure diagnosis.',),'attention'
    if status in ('FAILED','FAILED_USER','FAILED_METRIC'):
        return 'Check needs attention',('The expected response was not','confirmed within this check.','Review details and connections.'),'attention'
    feature=getattr(result,'feature_id','')
    if feature=='R04':
        return 'Klipper tuning suggestion',('Measured shaper values available.','Not saved to printer.cfg.'),'normal'
    if feature in ('H02','H03','H04'):
        return 'Calibration completed',('Klipper calculated PID values.','Saving is a separate decision.','Run a check after tuning.'),'normal'
    if status is None or status=='OBSERVED':
        return 'Information received',('This is a status observation,','not a hardware health test.'),'normal'
    if status in ('PASSED_USER','OBSERVED_USER'):
        return 'Function observed',('Your observation was recorded.','This confirms the tested function,','not precision or remaining life.'),'normal'
    return 'Check completed',('Evidence was captured for this','check. Details are optional.'),'normal'


def result_details(result):
    lines=[]
    outcomes=getattr(result,'components',()) or (result,)
    for outcome in outcomes:
        feature=getattr(outcome,'feature_id','')
        if feature:
            try: title=LABELS.get(feature,definition_for(feature).title)
            except ValueError: title='Check'
            lines.append(title)
        lines.append(str(getattr(outcome,'status',None) or 'OBSERVED'))
        reason=str(getattr(outcome,'reason',''))
        if reason: lines.append(reason.replace('_',' '))
        for key,value in getattr(outcome,'evidence',())[:16]:
            if feature=='R02' and key=='peak_hz':
                continue
            lines.append(str(key).replace('_',' ')+': '+str(value))
    restored=getattr(result,'restore_verified',None)
    if restored is not None:
        lines.append('Restore verified: '+('yes' if restored else 'not proven'))
    return tuple(lines)
