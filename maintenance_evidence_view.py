"""User-facing bounded diagnostic facts; raw transport codes stay in reports."""
import math
import re

FIELDS={
 'samples':('Samples',''),'span_s':('Measured span','s'),'rise_c':('Temperature rise','C'),
 'heating_c_per_s':('Heating rate','C/s'),'time_to_target_s':('Time to target','s'),
 'overshoot_c':('Overshoot','C'),'stability_peak_to_peak_c':('Variation','C'),
 'cooling_c_per_s':('Cooling rate','C/s'),'temperature':('Temperature','C'),
 'target':('Target','C'),'cpu_temp_c':('Host temperature','C'),'ambient_c':('Ambient','C'),
 'minimum_mm':('Minimum','mm'),'maximum_mm':('Maximum','mm'),'mean_mm':('Average','mm'),
 'diameter_mm':('Filament diameter','mm'),'commanded_mm':('Requested travel','mm'),
 'measured_mm':('Measured travel','mm'),'error_mm':('Travel difference','mm'),
 'frequency_hz':('Frequency','Hz'),'belt_a_peak_hz':('Belt A peak','Hz'),
 'belt_b_peak_hz':('Belt B peak','Hz'),'force_g':('Force','g'),'change_g':('Change','g'),
 'reference_grams':('Reference mass','g'),'total_jobs':('Recorded jobs',''),
 'total_time':('Recorded job time','s'),'total_print_time':('Recorded print time','s'),
 'total_filament_used':('Recorded filament','mm'),'rx_error':('Receive errors',''),
 'tx_error':('Transmit errors',''),'tx_retries':('Transmit retries',''),
 'buffered_events':('Buffered events',''),'error_events':('Error events',''),
 'configuration_warnings':('Config warnings',''),'x_mm':('X travel','mm'),
 'y_mm':('Y travel','mm'),'z_mm':('Z travel','mm'),
 'pid_Kp':('PID P',''),'pid_Ki':('PID I',''),'pid_Kd':('PID D',''),
 'Kp':('PID P',''),'Ki':('PID I',''),'Kd':('PID D','')}
ERRORS={'webhook_shutdown':'Safety shutdown','timer_too_close':'Timing warning',
 'communication_lost':'Connection lost','move_out_of_range':'Travel outside limits',
 'heater_response':'Heating response warning','adc_range':'Sensor range warning',
 'unknown_command':'Unsupported command','none_classified':'No classified error'}


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def _format(value,unit=''):
    return ('%.4g'%value)+((' '+unit) if unit else '')


def evidence_lines(feature,evidence):
    """Bounded whitelist: no raw flag/status/reason names in the user interface."""
    lines=[]
    omitted=False
    for key,value in tuple(evidence)[:32]:
        if key in FIELDS and _number(value):
            name,unit=FIELDS[key]
            lines.append(name+': '+_format(value,unit))
        elif key=='peak_hz' and feature!='R02' and _number(value):
            lines.append('Measured peak: '+_format(value,'Hz'))
        elif key in ('pwm_lower','pwm_upper') and _number(value):
            lines.append(('Start lower: ' if key=='pwm_lower' else 'Start upper: ')+_format(100*value/255,'%'))
        elif key=='power' and _number(value):
            lines.append('Heater output: '+_format(value*100,'%'))
        elif key.startswith('cpu.') and _number(value):
            suffix=key[4:]
            name='Core '+suffix[3:] if re.fullmatch(r'cpu[0-9]{1,2}',suffix) else 'CPU load'
            lines.append(name+': '+_format(value,'%'))
        elif key.startswith('memory.') and key[7:] in ('total','available','used') and _number(value):
            lines.append('Memory '+key[7:]+': '+_format(value/1024,'MiB'))
        elif key in ('total_bytes','used_bytes','free_bytes') and _number(value):
            lines.append('Disk '+key.partition('_')[0]+': '+_format(value/1073741824,'GiB'))
        elif key=='throttled_bits' and type(value) is int:
            lines.append('Host power / throttling')
            lines.append('Current warning: '+('yes' if value&15 else 'none'))
            lines.append('Earlier warning: '+('recorded' if value&0xF0000 else 'none recorded'))
        elif key=='last_error_code' and value in ERRORS:
            lines.append(ERRORS[value])
        elif key=='webhooks_state' and value in ('ready','startup','error','shutdown'):
            lines.append('Printer: '+{'ready':'ready','startup':'starting','error':'needs attention','shutdown':'stopped'}[value])
        elif key=='shaper' and isinstance(value,str) and re.fullmatch(r'[a-z0-9_]{1,16}',value):
            lines.append('Shaper: '+value.upper())
        elif key=='axis' and isinstance(value,str) and value.upper() in ('X','Y','Z','E'):
            lines.append('Axis: '+value.upper())
        elif key.endswith('.available') and type(value) is bool:
            lines.append('Update '+('available' if value else 'not pending'))
        elif key.endswith('.current') and isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9.+_-]{1,48}',value):
            lines.append(key[:-8].replace('_',' ')[:18]+': '+value)
        elif key.endswith(('.rx_bytes','.tx_bytes')) and _number(value):
            interface,_,direction=key.rpartition('.')
            lines.append(interface[:10]+(' received: ' if direction=='rx_bytes' else ' sent: ')+_format(value/1024,'KiB'))
        elif key=='value' and _number(value):
            lines.append('Reading: '+_format(value))
        elif key=='value' and isinstance(value,str) and len(value)<=80 and re.fullmatch(r'[A-Za-z0-9 .,:/+%()=-]+',value):
            lines.append(value)
        elif key in ('saved','authoritative_source','eventtime_s','klipper_eventtime_s'):
            continue
        else:
            omitted=True
    if omitted:
        lines.append('More evidence in support report.')
    if not lines:
        lines.append('No displayable measurement.')
    return tuple(lines[:48])


def outcome_text(status):
    return {None:'Information recorded','OBSERVED':'Information recorded',
        'PASSED':'Measured response confirmed','PASSED_USER':'User observation confirmed',
        'OBSERVED_USER':'User observation recorded','FAILED_METRIC':'Measurement needs review',
        'FAILED_USER':'Expected response not confirmed','FAILED':'Expected response not confirmed',
        'ERROR':'Check could not finish','BLOCKED':'Preparation required',
        'INCONCLUSIVE':'Not enough evidence','ABORTED':'Check stopped'}.get(status,'Evidence recorded')
