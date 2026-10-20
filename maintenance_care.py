"""Pure care classes and passive inventory, independent of executable checks."""
from collections.abc import Mapping

MAX_CARE_DEVICES = 256
TASKS = {
    'mechanical':'Mechanical maintenance',
    'filament_feed':'Filament feed maintenance',
    'nozzle':'Nozzle maintenance',
    'heating':'Heating system maintenance',
    'fan':'Fan maintenance',
    'lighting':'Lighting maintenance',
    'connected_device':'Connected device maintenance',
    'actuator':'Actuator maintenance',
    'sensor':'Sensor maintenance',
    'electronics':'Electronics maintenance',
    'general':'General hardware maintenance',
    # Persisted legacy task IDs remain readable; no automatic merge/reset.
    'inspect_clean':'General hardware maintenance',
    'lubricate':'Mechanical maintenance',
    'nozzle_inspect':'Nozzle maintenance',
}
SENSOR_PREFIXES = ('filament_switch_sensor ', 'filament_motion_sensor ',
    'hall_filament_width_sensor', 'tsl1401cl_filament_width_sensor',
    'temperature_sensor ', 'temperature_host ', 'temperature_mcu ',
    'temperature_probe ', 'probe_eddy_current ', 'load_cell ',
    'bme280 ', 'htu21d ', 'sht3x ', 'aht10 ', 'gcode_button ',
    'adxl345 ', 'lis2dw ', 'lis3dh ', 'mpu9250 ', 'icm20948 ')
PROBES = ('probe','bltouch','smart_effector','load_cell_probe','load_cell')


def family(device):
    if device.startswith(('endstop ',)+SENSOR_PREFIXES) or device in PROBES:
        return 'sensor'
    if device.startswith(('stepper_','axis_','manual_stepper ')):
        return 'mechanical'
    if device=='extruder' or device.startswith('extruder') and device[8:].isdigit():
        return 'extruder'
    if device=='heater_bed' or device.startswith('heater_generic '):
        return 'heating'
    if device=='fan' or device.startswith(('fan_generic ','heater_fan ','controller_fan ','temperature_fan ')):
        return 'fan'
    if device.startswith(('led ','neopixel ','dotstar ','pca9533 ','pca9632 ')):
        return 'lighting'
    if device.startswith(('output_pin ','pwm_cycle_time ','pwm_tool ')):
        return 'connected_device'
    if device.startswith('servo '):
        return 'actuator'
    if device=='mcu' or device.startswith(('mcu ','tmc2130 ','tmc2208 ','tmc2209 ',
        'tmc2240 ','tmc2660 ','tmc5160 ','tmc5161 ')):
        return 'electronics'
    return 'general'


def tasks(device):
    kind=family(device)
    return ('filament_feed','nozzle','heating') if kind=='extruder' else (kind,)


def task_label(task,device):
    if task=='inspect_clean':
        kind=family(device)
        return TASKS['heating' if kind=='extruder' else kind]
    return TASKS.get(task,'Service task')


def inventory(objects,settings,existing=()):
    """Called once at READY. No pin probing, subscriptions, or test permissions.

    Config-only sensors/probes count as configured hardware, not live readings.
    Endstop identities are per configured motor; virtual endstops are excluded.
    """
    settings=settings if isinstance(settings,Mapping) else {}
    names=set(existing)
    for name in set(objects)|set(settings):
        if not isinstance(name,str): continue
        if family(name)!='general': names.add(name)
    # BLTouch/smart-effector status is commonly published under `probe`.
    if 'probe' in objects:
        names.difference_update(('bltouch','smart_effector'))
    for name,cfg in settings.items():
        if (isinstance(name,str) and name.startswith(('stepper_x','stepper_y','stepper_z'))
                and name[9:].isdigit() or name in ('stepper_x','stepper_y','stepper_z')):
            pin=cfg.get('endstop_pin') if isinstance(cfg,Mapping) else None
            if isinstance(pin,str) and pin.strip() and 'virtual_endstop' not in pin:
                names.add('endstop '+name)
    valid=sorted(n for n in names if isinstance(n,str) and len(n.encode('utf-8'))<=96)
    return tuple(valid[:MAX_CARE_DEVICES]),len(names)-min(len(valid),MAX_CARE_DEVICES)
