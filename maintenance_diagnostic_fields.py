"""Presentation of the actual bounded information-reader contracts.

No device reads, raw flag labels, guessed units or hardware health verdicts.
"""
import math
import re

COUNTERS={
 'reported_nonzero_fields':'Reported driver fields','fault_count':'Driver alerts',
 'captures':'Recorded captures','recorded_results':'Saved check results','linked_spools':'Linked spools',
 'results':'Exported results','tx_frames':'UART frames sent','tx_bytes':'UART bytes sent',
 'rx_bytes':'UART bytes received','handshake_requests':'Panel handshakes',
 'crc_notifications':'CRC notifications','response_timeouts':'Response timeouts',
 'responses':'Discarded replies','aux':'Discarded auxiliary data','uart_epoch':'Panel session',
 'gpio_button_presses':'Button presses','gpio_positive_steps':'Clockwise steps',
 'gpio_negative_steps':'Counterclockwise steps',
 'homing_cycles':'Homing cycles','reported_errors':'Reported errors','declared_angles':'Observed angles',
 'acknowledged_steps':'Completed service steps'}
DRIVER_FLAGS={
 'ot':'Thermal shutdown','otpw':'Temperature warning','s2ga':'Coil A short to ground',
 's2gb':'Coil B short to ground','s2vsa':'Coil A short to supply','s2vsb':'Coil B short to supply',
 'ola':'Coil A open-load flag','olb':'Coil B open-load flag','stst':'Standstill',
 't120':'120 C threshold','t143':'143 C threshold','t150':'150 C threshold','t157':'157 C threshold'}
NUMBERS={
 'run_current':('Run current','A'),'hold_current':('Hold current','A'),
 'max_velocity_mm_s':('Velocity limit','mm/s'),'humidity_pct':('Humidity','%'),
 'humidity':('Humidity','%'),'pressure':('Pressure','hPa'),'gas':('Gas resistance','ohm'),
 'declared_used_mm':('Declared filament use','mm'),
 'average_mm':('Average','mm'),'peak_shift_hz':('Peak shift','Hz'),
 'spectral_similarity':('Spectrum similarity',''),'range_mm':('Range','mm'),'median_mm':('Median','mm'),'sigma_mm':('Std deviation','mm'),
 'standard_deviation_mm':('Std deviation','mm'),'stddev_mm':('Std deviation','mm'),
 'preparation_z_lift_mm':('Clearance lift','mm'),
 'pid_kp':('PID P',''),'pid_ki':('PID I',''),'pid_kd':('PID D',''),
 'x_mm_s2':('X acceleration','mm/s2'),'y_mm_s2':('Y acceleration','mm/s2'),
 'z_mm_s2':('Z acceleration','mm/s2'),'frequency_ratio':('Frequency ratio',''),
 'AC_mm':('Diagonal AC','mm'),'BD_mm':('Diagonal BD','mm'),'AD_mm':('Side AD','mm'),
 'minimum_mm':('Minimum','mm'),'maximum_mm':('Maximum','mm')}
BOOLS={
 'startup_assets_synced':('Panel artwork','Synchronized','Not synchronized'),
 'wear_measured':('Wear measurement','Measured','Not measured'),
 'report_ready':('Report export','Ready','Not ready'),
 'baseline_saved':('Reference','Saved','Not saved'),
 'modal_restore_verified':('Motion settings','Restored','Not confirmed'),
 'pwm_restore_verified':('Output setting','Restored','Not confirmed'),
 'firmware_state_confirmed':('Firmware state','Confirmed','Not confirmed'),
 'firmware_guided_completed':('Guided operation','Completed','Not completed'),
 'deploy_rpc':('Probe deploy command','Completed','Not completed'),
 'stow_rpc':('Probe stow command','Completed','Not completed'),
 'applied':('Calibration','Applied for this session','Not applied')}

def number(value):
    return type(value) in (int,float) and math.isfinite(value)

def text(value):
    return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9 _.,:/+%()=\[\]-]{1,96}',value))

def name(value):
    from maintenance_experience import device_name
    return device_name(value) if isinstance(value,str) else 'Printer'

def formatted(value,unit=''):
    return ('%.4g'%value)+((' '+unit) if unit else '')

def duration(value):
    seconds=max(0,int(value))
    days,seconds=divmod(seconds,86400)
    hours,seconds=divmod(seconds,3600)
    minutes,seconds=divmod(seconds,60)
    return (('%dd '%days if days else '')+('%dh '%hours if hours or days else '')+
            ('%dm '%minutes if minutes or hours or days else '')+('%ds'%seconds)).strip()

def _flags(value):
    if value=='none reported': return 'None reported'
    if not text(value): return None
    flags=value.split(',')
    if not all(f in DRIVER_FLAGS for f in flags): return None
    return ', '.join(DRIVER_FLAGS[f] for f in flags)

def diagnostic_lines(feature,key,value):
    """None = unknown/internal. A tuple is an explicitly interpreted field."""
    if key in NUMBERS and number(value):
        label,unit=NUMBERS[key]
        return (label+': '+formatted(value,unit),)
    if key in COUNTERS and number(value):
        return (COUNTERS[key]+': '+(str(int(value)) if value==int(value) else formatted(value)),)
    if key in BOOLS and type(value) is bool:
        label,yes,no=BOOLS[key]
        return (label+': '+(yes if value else no),)
    if feature=='M07':
        if key in DRIVER_FLAGS and type(value) in (bool,int) and value in (0,1):
            return (DRIVER_FLAGS[key]+': '+('Reported' if value else 'Not reported'),)
        if key in ('standstill','stealth') and type(value) in (bool,int) and value in (0,1):
            return ((('Standstill: '+('Yes' if value else 'No')) if key=='standstill' else
                     'Drive mode: '+('Quiet' if value else 'Standard')),)
        if key=='cs_actual' and type(value) is int and 0<=value<=31:
            return ('Current scale: %d/31'%value,)
        if key=='register' and value=='DRV_STATUS': return ()
        if key=='register_hex' and isinstance(value,str) and re.fullmatch(r'[0-9A-Fa-f]{8}',value):
            return ('Status register: 0x'+value.upper(),)
        if key in ('faults','open_load_flags'):
            interpreted=_flags(value)
            if interpreted is not None:
                lines=(('Driver alerts' if key=='faults' else 'Coil load flags')+': '+interpreted,)
                return lines+(('Open-load flags can appear at rest.',) if key=='open_load_flags' else ())
        if key=='decode' and value in ('unknown register bits','chip-specific interpretation required'):
            return ('Interpretation: '+('Unknown register bits' if value=='unknown register bits' else
                                       'Not decoded for this driver'),)
    if feature=='M11' and text(key) and type(value) is bool:
        return (name(key)+': '+('Enabled' if value else 'Disabled'),)
    if feature=='M12' and key.endswith('.phase') and text(value):
        return (name(key[:-6])+' phase: '+value,)
    if feature=='M13' and key.endswith('.temperature') and number(value):
        return (name(key[:-12])+' temperature: '+formatted(value,'C'),)
    if feature=='M14':
        if key=='homed_axes' and isinstance(value,str) and (value=='none' or set(value)<=set('xyz')):
            return ('Homed axes: '+('None' if value in ('none','') else ' '.join(value.upper())),)
        if key in ('commanded_x','commanded_y','commanded_z') and number(value):
            return ('Commanded '+key[-1].upper()+': '+formatted(value,'mm'),)
    if feature=='M16' and key in ('carriage_0','carriage_1','active_carriage'):
        if key=='active_carriage' and type(value) is int and value in (0,1):
            return ('Active carriage: '+str(value),)
        modes={'PRIMARY':'Primary','INACTIVE':'Inactive','COPY':'Copy','MIRROR':'Mirror'}
        if isinstance(value,str) and value in modes:
            return (key.replace('_',' ').capitalize()+': '+modes[value],)
    if feature=='S06':
        source,sep,field=key.rpartition('.')
        names={'mcu_awake':('active time','s',1),'mcu_task_avg':('task average','us',1e6),
               'mcu_task_stddev':('task variation','us',1e6)}
        if sep and (source=='mcu' or source.startswith('mcu ')) and field in names and number(value):
            label,unit,scale=names[field]
            source='MCU'+(' '+source[4:] if source.startswith('mcu ') else '')
            return (source+' '+label+': '+formatted(value*scale,unit),)
    if key=='bus_state':
        states={'active':'Active','passive':'Passive','off':'Off','error-active':'Error active',
                'error-passive':'Error passive','bus-off':'Bus off'}
        if isinstance(value,str) and value in states: return ('CAN state: '+states[value],)
    if feature=='S11' and re.fullmatch(r'recent_[0-4]',key) and isinstance(value,str):
        feature_id,sep,status=value.partition(' ')
        from maintenance_catalog import definition_for
        from maintenance_evidence_view import outcome_text
        try: title=definition_for(feature_id).title
        except ValueError: return None
        return ('Recent check '+str(int(key[-1])+1)+': '+title+' / '+outcome_text(None if status=='None' else status),)
    if feature=='S13':
        if key in ('x_mm','y_mm','z_mm') and number(value) and value>=0:
            return (key[0].upper()+' travel this session: '+formatted(value/1000,'m'),)
        if key=='coverage' and value=='recorded_lower_bound_this_session':
            return ('Recorded session lower bound; homing and probing excluded.',)
        if key=='dropped_batches' and number(value):
            return ('Excluded intervals/moves: '+str(int(value)),)
        if key=='tracking_state' and value in ('starting','tracking','paused','unavailable'):
            return ('Axis tracking: '+value,)
    if feature=='S12':
        # Usage History is quantities only. Event kinds, live tracking state
        # and capacity are preserved in the raw evidence but not drawn.
        if key in ('coverage','sensor_coverage','sensor_event_coverage',
                   'travel_tracking','usage_slots_remaining','usage_tracking_omitted'):
            return ()
        if key.endswith(('.observed_trigger_count','.sensor_tracking',
                         '.event_kind','.event_tracking','.tracking_state')):
            return ()
        if key.endswith('.trigger_count') and type(value) is int and value>=0:
            return (name(key[:-len('.trigger_count')])+': '+str(value)+' events recorded',)
        if key.endswith('.travel_mm') and number(value) and value>=0:
            return (name(key[:-10])+': '+formatted(value/1000,'m'),)
        if key=='sampled_print_s' and number(value):
            return ('Sampled print time: '+duration(value),)
        if key.endswith('.sampled_on_s') and number(value) and value>=0:
            return (name(key[:-13])+' ON time: '+duration(value),)
    if feature=='S10' and key in ('total_time','total_print_time') and number(value) and value>=0:
        return (('Recorded job time' if key=='total_time' else 'Recorded print time')+': '+duration(value),)
    if feature=='S10' and key=='total_filament_used' and number(value):
        return ('Recorded filament: '+formatted(value/1000,'m'),)
    if feature=='E06' and key=='coverage' and value=='explicit_captures_only':
        return ('Only explicitly captured diameter samples are included.',)
    if feature=='S20' and key=='download' and value=='maintenance-report.json':
        return ('Report file: maintenance-report.json',)
    if key in ('data','next') and value in ('Klipper PSD recorded','Run R04 for Klipper fit'):
        return (('Vibration spectrum recorded.' if key=='data' else 'Run Input Shaper tuning for a Klipper recommendation.'),)
    if key=='trigger_phase' and text(value): return ('Trigger phase: '+value,)
    if key=='phase_count' and number(value): return ('Phase positions: '+formatted(value),)
    return None
