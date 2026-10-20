"""Semantic icon selection from action/feature contracts, never label guesses."""
from lcd_resources import (ICON_MAINTENANCE_CHECK,ICON_MAINTENANCE_DIAGNOSTICS,
    ICON_MAINTENANCE_RECOMMENDATIONS,ICON_MAINTENANCE_CARE,
    ICON_MOTION,ICON_PROBE_CALIBRATION,ICON_LIGHT,ICON_BUZZER,ICON_ENCODER_TONE,
    ICON_HOST,ICON_MCU,ICON_SOFTWARE,ICON_POWER,ICON_SCREW_ADJUST,ICON_SAVE_PROFILE)

TOPICS={'thermal':40,'motion':ICON_MOTION,'geometry':ICON_PROBE_CALIBRATION,
        'filament':38,'cooling':48,'vibration':ICON_MAINTENANCE_DIAGNOSTICS,
        'system':ICON_HOST,'auxiliary':ICON_LIGHT}
FAMILIES=dict(F='cooling',H='thermal',M='motion',P='geometry',R='vibration',E='filament',S='system',O='auxiliary')
PAGES={'groups':ICON_MAINTENANCE_CHECK,'diagnostic_groups':ICON_MAINTENANCE_DIAGNOSTICS,
       'diagnostics':ICON_MAINTENANCE_DIAGNOSTICS,'service':ICON_MAINTENANCE_CARE,
       'calibrations':58,'support':14,'more':26,'sensor_devices':30}


def device_icon(device):
    device=device or ''
    if device.startswith('extruder'): return 9
    if device=='heater_bed': return 10
    if device.startswith('heater_'): return 40
    if device.startswith(('stepper_','axis_','manual_stepper ')): return 27
    if device.startswith('endstop '): return 30
    if device.startswith('tmc'): return ICON_MCU
    if device.startswith(('fan','heater_fan ','controller_fan ')): return 48
    if device.startswith(('neopixel ','led ','output_pin ')): return ICON_LIGHT
    if 'buzzer' in device: return ICON_BUZZER
    if 'probe' in device: return ICON_PROBE_CALIBRATION
    if device.startswith('mcu'): return ICON_MCU
    return None


def feature_icon(feature,device=None):
    specific={'M01':30,'M03':29,'M07':ICON_MCU,'M10':ICON_MCU,'M12':30,
        'S01':ICON_HOST,'S02':204,'S03':ICON_POWER,'S04':14,'S05':ICON_HOST,
        'S06':ICON_MCU,'S07':ICON_MCU,'S08':ICON_SOFTWARE,'S09':14,'S10':15,
        'S11':15,'S12':15,'S13':27,'S14':ICON_SOFTWARE,'S15':ICON_ENCODER_TONE,
        'S16':ICON_MAINTENANCE_DIAGNOSTICS,'S17':211,'S18':ICON_BUZZER,
        'S19':ICON_SOFTWARE,'S20':14,'O04':ICON_LIGHT}
    if feature in specific: return specific[feature]
    if feature in ('H02','H03','H04'): return 58
    if feature.startswith('H'): return 10 if device=='heater_bed' else 9
    return TOPICS.get(FAMILIES.get(feature[:1]))


def icon_for(choice):
    action,value=choice.action,choice.value
    if action=='none': return None
    if action in ('back','home','result_back'): return 13
    if action=='open': return PAGES.get(value)
    if action in ('prepare','read'):
        return feature_icon(getattr(value,'feature_id',''),getattr(value,'device',None))
    if action=='targets': return TOPICS.get(value[1])
    if action=='diagnostic_topic': return TOPICS.get(value)
    if action=='findings': return ICON_MAINTENANCE_RECOMMENDATIONS
    if action=='finding':
        finding=value[0] if isinstance(value,tuple) else value
        features=getattr(finding,'evidence_features',())
        return feature_icon(features[0],finding.device) if features else device_icon(finding.device)
    if action in ('service','service_add','service_basis','service_kind'): return ICON_MAINTENANCE_CARE
    if action=='service_device': return device_icon(value)
    if action=='service_task':
        policy=value[0]
        return ICON_SCREW_ADJUST if policy.task_id in ('lubricate','mechanical') else 38 if policy.task_id in ('nozzle_inspect','nozzle','filament_feed') else ICON_MAINTENANCE_CARE
    if action in ('history','load_history','history_read'): return 15
    if action=='historical_result': return feature_icon(value.get('feature',''),value.get('device'))
    if action=='load_services': return 43
    if action in ('trace','export','instructions'): return 14
    if action=='leveling': return ICON_PROBE_CALIBRATION
    if action=='details': return 45
    if action in ('reference','reference_limit','reference_confirm'): return 202
    if action in ('service_save','service_complete'): return ICON_SAVE_PROFILE
    return None
