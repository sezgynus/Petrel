"""Printer position, editor values and material preset records."""
import copy
import math
from collections.abc import Mapping


class xyze_t:
    x = 0.0
    y = 0.0
    z = 0.0
    e = 0.0
    home_x = False
    home_y = False
    home_z = False

    def homing(self):
        self.home_x = False
        self.home_y = False
        self.home_z = False

class AxisEnum:
    X_AXIS = 0
    A_AXIS = 0
    Y_AXIS = 1
    B_AXIS = 1
    Z_AXIS = 2
    C_AXIS = 2
    E_AXIS = 3
    X_HEAD = 4
    Y_HEAD = 5
    Z_HEAD = 6
    E0_AXIS = 3
    E1_AXIS = 4
    E2_AXIS = 5
    E3_AXIS = 6
    E4_AXIS = 7
    E5_AXIS = 8
    E6_AXIS = 9
    E7_AXIS = 10
    ALL_AXES = 0xFE
    NO_AXIS = 0xFF

class HMI_value_t:
    E_Temp = 0
    Bed_Temp = 0
    Fan_speed = 0
    print_speed = 100
    Max_Feedspeed = 0.0
    Max_Acceleration = 0.0
    Max_Jerk = 0.0
    Max_Step = 0.0
    Move_X_scale = 0.0
    Move_Y_scale = 0.0
    Move_Z_scale = 0.0
    Move_E_scale = 0.0
    offset_value = 0.0
    show_mode = 0  # -1: Temperature control    0: Printing temperature

class HMI_Flag_t:
    language = 0
    pause_flag = False
    pause_action = False
    print_finish = False
    done_confirm_flag = False
    select_flag = False
    home_flag = False
    heat_flag = False  # 0: heating done  1: during heating
    ETempTooLow_flag = False
    leveling_offset_flag = False
    feedspeed_axis = AxisEnum()
    acc_axis = AxisEnum()
    jerk_axis = AxisEnum()
    step_axis = AxisEnum()

class buzz_t:
    def tone(self, t, n):
        pass

class material_preset_t:
    def __init__(self, name, hotend_temp=0, bed_temp=0, mainsail_id=None, mainsail_raw=None):
        self.name = str(name)
        self.hotend_temp = hotend_temp
        self.bed_temp = bed_temp
        self.mainsail_id = mainsail_id
        self.mainsail_raw = copy.deepcopy(mainsail_raw) if mainsail_raw is not None else None

    @classmethod
    def from_mainsail(cls, preset, preset_id=None):
        if not isinstance(preset, Mapping) or not str(preset.get('name', '')).strip():
            raise ValueError('Invalid Mainsail preset')
        hotend = bed = 0.0
        values = preset.get('values', {})
        if not isinstance(values, Mapping):
            raise ValueError('Invalid Mainsail preset values')
        for device, setting in values.items():
            if not isinstance(setting, Mapping) or not setting.get('bool', False):
                continue
            value = setting.get('value')
            if isinstance(value, bool):
                raise ValueError('Invalid Mainsail preset value')
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError('Invalid Mainsail preset value')
            if not math.isfinite(value):
                raise ValueError('Invalid Mainsail preset value')
            if value.is_integer():
                value = int(value)
            if device == 'extruder':
                hotend = value
            elif device == 'heater_bed':
                bed = value
        return cls(str(preset['name']).strip(), hotend, bed, preset_id, preset)
