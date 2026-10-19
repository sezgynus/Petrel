from lcd_resources import ICON_ACCELERATION, ICON_BRIGHTNESS, ICON_BUZZER, ICON_CLICK_TONE, ICON_CORNER_SPEED, ICON_CRUISE_RATIO, ICON_DIM_BRIGHTNESS, ICON_ENCODER_TONE, ICON_FLOW, ICON_IDLE_DIM, ICON_LIGHT, ICON_LIVE_JOG, ICON_MOTION, ICON_MOTOR_OFF, ICON_PREHEAT_PROFILE, ICON_VELOCITY, ICON_VOLUME
from graphite_theme import show_icon as show_theme_icon, draw_scrollbar
from lcd_resources import ICON_POWER_BUTTON_NORMAL, ICON_POWER_BUTTON_CANCEL, ICON_POWER_BUTTON_OFF
from lcd_resources import ICON_INFO_UPDATE_SELECTED, ICON_INFO_UPDATE_NORMAL
from lcd_resources import ICON_FAN_FIRST, ICON_FAN_LAST, ICON_LIBRARY_ID, ICON_CHECKBOX_EMPTY, ICON_CHECKBOX_CHECKED
import display_settings
import copy
import textwrap
from software_update import SoftwareUpdate
from info_qr import PROJECT_URL, draw_project_qr, extra_info_rows
from shared_artwork import PICTURE_ID as SHARED_PICTURE_ID
from system_info import wifi_signal_text
import time
import logging
from concurrent.futures import Future
from command_feedback import CommandFeedback
from threading import Lock
from ui_events import UIEventLoop, InputEvent
from ui_case_light import CaseLightMixin
from ui_maintenance import MaintenanceViewMixin
from ui_recovery import RecoveryViewMixin
from ui_power import PowerShortcutMixin
from ui_mmu import MMUViewMixin
from ui_buzzer import BuzzerViewMixin
import buzzer_control
from buzzer_control import Settings as BuzzerSettings
from ui_screws_tilt import ScrewsTiltMixin
from ui_bed_mesh import BedMeshMixin
from ui_file_preview import FilePreviewMixin
from ui_print_focus import PrintFocusMixin
from power_lifecycle import PowerMonitor
from uart_startup import PanelProbe

from encoder import Encoder
from gpiozero import Button, Device
from gpiozero.pins.lgpio import LGPIOFactory
from printerInterface import PrinterData
from t5uic1_driver import T5UIC1Display, T5UIC1ProtocolError
from lcd_resources import ICON_FOLDER, ICON_MCU, ICON_MACHINE, ICON_HOST, ICON_SOFTWARE, ICON_POWER, ICON_DISPLAY_NORMAL, ICON_DISPLAY_SELECTED, ICON_MMU_HOME_NORMAL, ICON_MMU_HOME_SELECTED

def _MAX(lhs, rhs):
    if lhs > rhs:
        return lhs
    else:
        return rhs


class select_t:
    def __init__(self):
        self.now = 0
        self.last = 0

    def set(self, v):
        self.now = self.last = v

    def reset(self):
        self.set(0)

    def changed(self):
        c = (self.now != self.last)
        if c:
            self.last = self.now
            return c

    def dec(self):
        if (self.now):
            self.now = max(0,self.now-getattr(self,"batch_steps",1))
        return self.changed()

    def inc(self, v):
        if (self.now < (v - 1)):
            self.now = min(v-1,self.now+getattr(self,"batch_steps",1))
        else:
            self.now = (v - 1)
        return self.changed()


class PetrelDisplay(RecoveryViewMixin, PrintFocusMixin, PowerShortcutMixin, BuzzerViewMixin, MMUViewMixin, CaseLightMixin, MaintenanceViewMixin, ScrewsTiltMixin, BedMeshMixin, FilePreviewMixin):

    TROWS = 6
    MROWS = TROWS - 1  # Total rows, and other-than-Back
    TITLE_HEIGHT = 30  # Title bar height
    MLINE = 53         # Menu line height
    LBLX = 60          # Menu item label X
    MENU_CHR_W = 8
    STAT_CHR_W = 10


    MSG_STOP_PRINT = "Stop Print"
    MSG_PAUSE_PRINT = "Pausing..."

    DWIN_SCROLL_UP = 2
    DWIN_SCROLL_DOWN = 3

    SELECTIONS = ('select_page', 'select_file', 'select_print', 'select_prepare',
                  'select_control', 'select_axis', 'select_temp',
                  'select_motion', 'select_tune', 'select_PLA', 'select_ABS', 'select_light')

    index_file = MROWS
    index_prepare = MROWS
    index_control = MROWS
    index_temp = MROWS
    index_tune = MROWS

    MainMenu = 0
    SelectFile = 1
    Prepare = 2
    Control = 3
    Leveling = 4
    PrintProcess = 5
    AxisMove = 6
    TemperatureID = 7
    Motion = 8
    Info = 9
    Tune = 10
    PLAPreheat = 11
    ABSPreheat = 12

    # Last Process ID
    Last_Prepare = 21

    # Back Process ID
    Back_Main = 22

    # Date variable ID
    Move_X = 24
    Move_Y = 25
    Move_Z = 26
    Extruder = 27
    ETemp = 28
    Homeoffset = 29
    BedTemp = 30
    FanSpeed = 31
    PrintSpeed = 32

    Print_window = 33
    ProbeWizardID = 36
    MotionValue = 35
    CaseLight = 37
    CaseLightBrightness = 38
    ScrewsTiltMenu = 39
    ScrewsTiltResult = 40
    BedMeshScreen = 41
    MeshProfiles = 42
    BedMeshMenu = 43
    MMUMenu = 44
    FilePreview = 45
    PowerConfirm = 46
    DisplayMenu = 47
    MaintenanceMenu = 48
    BuzzerMenu = 49

    MINUNITMULT = 10

    ENCODER_DIFF_NO = 0  # no state
    ENCODER_DIFF_CW = 1  # clockwise rotation
    ENCODER_DIFF_CCW = 2  # counterclockwise rotation
    ENCODER_DIFF_ENTER = 3   # click
    ENCODER_WAIT_ENTER = 300
    ENCODER_ACCEL_START_STEPS_PER_SEC = 10
    ENCODER_ACCEL_FULL_STEPS_PER_SEC = 46
    ENCODER_FAST_MULTIPLIER = 250
    ENCODER_ACCEL_EXPONENT = 2.75
    _encoder_move_value = 1


    dwin_zoffset = 0.0
    last_zoffset = 0.0

    # ICON ID
    ICON = ICON_LIBRARY_ID

    ICON_LOGO = 0
    ICON_MMU_0 = ICON_MMU_HOME_NORMAL
    ICON_MMU_1 = ICON_MMU_HOME_SELECTED
    ICON_Display_0 = ICON_DISPLAY_NORMAL
    ICON_Display_1 = ICON_DISPLAY_SELECTED
    ICON_Print_0 = 1
    ICON_Print_1 = 2
    ICON_Prepare_0 = 3
    ICON_Prepare_1 = 4
    ICON_Control_0 = 5
    ICON_Control_1 = 6
    ICON_Leveling_0 = 7
    ICON_Leveling_1 = 8
    ICON_HotendTemp = 9
    ICON_BedTemp = 10
    ICON_Speed = 11
    ICON_Zoffset = 12
    ICON_Back = 13
    ICON_File = 14
    ICON_PrintTime = 15
    ICON_RemainTime = 16
    ICON_Setup_0 = 17
    ICON_Setup_1 = 18
    ICON_Pause_0 = 19
    ICON_Pause_1 = 20
    ICON_Continue_0 = 21
    ICON_Continue_1 = 22
    ICON_Stop_0 = 23
    ICON_Stop_1 = 24
    ICON_Bar = 25
    ICON_More = 26

    ICON_Axis = 27
    ICON_CloseMotor = ICON_MOTOR_OFF
    ICON_Homing = 29
    ICON_SetHome = 30
    ICON_PLAPreheat = ICON_PREHEAT_PROFILE
    ICON_ABSPreheat = 32
    ICON_Cool = 33
    ICON_Language = 34

    ICON_MoveX = 35
    ICON_MoveY = 36
    ICON_MoveZ = 37
    ICON_Extruder = 38

    ICON_Temperature = 40
    ICON_Motion = ICON_MOTION
    ICON_WriteEEPROM = 42
    ICON_ReadEEPROM = 43
    ICON_ResumeEEPROM = 44
    ICON_Info = 45
    ICON_CaseLight = ICON_LIGHT

    ICON_SetEndTemp = 46
    ICON_SetBedTemp = 47
    ICON_FanSpeed = 48
    ICON_SetPLAPreheat = 49
    ICON_SetABSPreheat = 50

    ICON_MaxSpeed = 51
    ICON_MaxAccelerated = 52
    ICON_MaxJerk = 53
    ICON_Step = 54
    ICON_PrintSize = 55
    ICON_Version = 56
    ICON_Contact = 57
    ICON_StockConfiguraton = 58
    ICON_MaxSpeedX = 59
    ICON_MaxSpeedY = 60
    ICON_MaxSpeedZ = 61
    ICON_MaxSpeedE = 62
    ICON_MaxAccX = 63
    ICON_MaxAccY = 64
    ICON_MaxAccZ = 65
    ICON_MaxAccE = 66
    ICON_MaxSpeedJerkX = 67
    ICON_MaxSpeedJerkY = 68
    ICON_MaxSpeedJerkZ = 69
    ICON_MaxSpeedJerkE = 70
    ICON_StepX = 71
    ICON_StepY = 72
    ICON_StepZ = 73
    ICON_StepE = ICON_FLOW
    ICON_Setspeed = 75
    ICON_SetZOffset = 76
    ICON_Rectangle = 77
    ICON_BLTouch = 78
    ICON_TempTooLow = 79
    ICON_AutoLeveling = 80
    ICON_TempTooHigh = 81
    ICON_NoTips_C = 82
    ICON_NoTips_E = 83
    ICON_Continue_C = 84
    ICON_Continue_E = 85
    ICON_Cancel_C = 86
    ICON_Cancel_E = 87
    ICON_Confirm_C = 88
    ICON_Confirm_E = 89
    ICON_Maintenance_0 = 90
    ICON_Maintenance_1 = 91
    ICON_Info_0 = 92
    ICON_Info_1 = 93

    MENU_CHAR_LIMIT = 24
    STATUS_Y = 360

    MOTION_CASE_RATE = 1
    MOTION_CASE_ACCEL = 2
    MOTION_CASE_JERK = MOTION_CASE_ACCEL + 0
    MOTION_CASE_STEPS = MOTION_CASE_JERK + 1
    MOTION_CASE_TOTAL = MOTION_CASE_STEPS

    PREPARE_CASE_MOVE = 1
    PREPARE_CASE_DISA = 2
    PREPARE_CASE_HOME = 3
    PREPARE_CASE_ZOFF = PREPARE_CASE_HOME + 1
    PREPARE_CASE_PLA = PREPARE_CASE_ZOFF + 1
    PREPARE_CASE_ABS = PREPARE_CASE_PLA + 1
    PREPARE_CASE_COOL = PREPARE_CASE_ABS + 1
    PREPARE_CASE_TOTAL = PREPARE_CASE_COOL

    CONTROL_CASE_TEMP = 1
    CONTROL_CASE_MOVE = 2
    CONTROL_CASE_INFO = 3
    CONTROL_CASE_TOTAL = 3

    TUNE_CASE_SPEED = 1
    TUNE_CASE_TEMP = (TUNE_CASE_SPEED + 1)
    TUNE_CASE_BED = (TUNE_CASE_TEMP + 1)
    TUNE_CASE_FAN = (TUNE_CASE_BED + 0)
    TUNE_CASE_ZOFF = (TUNE_CASE_FAN + 1)
    TUNE_CASE_TOTAL = TUNE_CASE_ZOFF

    TEMP_CASE_TEMP = (0 + 1)
    TEMP_CASE_BED = (TEMP_CASE_TEMP + 1)
    TEMP_CASE_FAN = (TEMP_CASE_BED + 0)
    TEMP_CASE_PLA = (TEMP_CASE_FAN + 1)
    TEMP_CASE_ABS = (TEMP_CASE_PLA + 1)
    TEMP_CASE_TOTAL = TEMP_CASE_ABS

    PREHEAT_CASE_TEMP = (0 + 1)
    PREHEAT_CASE_BED = (PREHEAT_CASE_TEMP + 1)
    PREHEAT_CASE_SAVE = (PREHEAT_CASE_BED + 1)
    PREHEAT_CASE_TOTAL = PREHEAT_CASE_SAVE

    # Dwen serial screen initialization
    # Passing parameters: serial port number
    # DWIN screen uses serial port 1 to send
    def __init__(self, USARTx, encoder_pins, button_pin, octoPrint_API_Key,
                 moonraker_url='http://127.0.0.1:7125', request_timeout=5.0, settings_path=None,
                 power_device='Printer', power_on_hold_ms=2000,
                 emulator=False, emulator_socket=None, screenshot_directory=None, emulator_font=None,
                 remote=False, remote_port=8088, remote_host='0.0.0.0'):
        self._closed = False
        self._uart_epoch = 0
        self._uart_online = False
        self._next_uart_retry = 0
        self._next_uart_probe = 0
        self._panel_probe = None
        self._uart_fast_until = 0
        self._uart_start_signal = None
        self._uart_probe_failures = 0
        self._boot_active = True
        self._boot_connection_started = None
        self._boot_connection_delayed = False
        self._boot_files_started = (None, 0)
        self._boot_progress = -1
        self.encoder = self.button = self.lcd = self.pd = None
        self._emulator_options = (bool(emulator or remote), emulator_socket, screenshot_directory, emulator_font)
        self._remote_options = (bool(remote), remote_port, remote_host)
        self._settings = (USARTx, encoder_pins, button_pin, octoPrint_API_Key,
                          moonraker_url, request_timeout, settings_path, power_device, power_on_hold_ms)
        self._input_lock = Lock()
        self._producer_value = 0
        self._last_press = float('-inf')
        self._last_encoder_time = None
        self._encoder_event = self.ENCODER_DIFF_NO
        self._encoder_move_value = 1
        self._live_jog = False
        self._live_jog_future = None
        self._live_jog_pending = None
        self._info_scroll = 0
        self._power_focus = False
        self._power_origin = None
        self._power_confirm_yes = True
        self._loop = UIEventLoop(self._initialize, self._process_input,
                                 self._ui_tick, self._close_resources, interval=.5)
        self._loop.start()

    def _initialize(self):
        enabled, socket_path, output, font = self._emulator_options
        if enabled:
            from dwin_emulator.runtime import Emulator, ScreenshotServer
            self._emulator = Emulator(enabled=True, font_path=font)
            self._screenshot_server = ScreenshotServer(self._emulator, socket_path, output)
        USARTx, encoder_pins, button_pin, api_key, url, timeout, settings_path, power_device, power_on_hold_ms = self._settings
        Device.pin_factory = LGPIOFactory()
        for name in self.SELECTIONS:
            setattr(self, name, select_t())
        self.encoder = Encoder(encoder_pins[0], encoder_pins[1])
        self.power_on_hold_ms = max(0, int(power_on_hold_ms))
        hold_time = max(0.001, self.power_on_hold_ms / 1000.0)
        self.button = Button(button_pin, pull_up=True, bounce_time=0.05,
                             hold_time=hold_time, hold_repeat=False)
        self.next_rts_update_ms = 0
        self.last_cardpercentValue = 101
        self.checkkey = self.MainMenu
        self.pd = PrinterData(api_key, url, timeout, settings_path=settings_path,
                              power_device=power_device)
        self._maintenance_button_presses = 0
        self.pd._maintenance_panel_api = self._maintenance_panel_api
        self.pd.init_Webservices()
        self._power_monitor = PowerMonitor(self.pd.client, self.pd.power_device)
        self._relay_status = None
        self._relay_off_serial = 0
        self._panel_backend_epoch = self.pd.subscription.snapshot()['epoch']
        self._configure_menus()
        self._offline = bool(self.pd.connection_error)
        self._poll_panel_power()
        self._ensure_uart()
        # Enable producers only after all UI/backend resources are initialized.
        with self._input_lock:
            self._producer_value = self.encoder.getValue()
            self.encoder.callback = self.encoder_has_data
        self.button.when_pressed = self._button_pressed
        self.button.when_released = self._button_released
        self.button.when_held = self._button_held
        if self._remote_options[0]:
            try:
                from dwin_emulator.remote import RemoteDisplayServer
                self._remote_display = RemoteDisplayServer(
                    self._emulator, self._remote_input,
                    port=self._remote_options[1], host=self._remote_options[2],
                    report_provider=self.pd.maintenance_book.exported,
                    trace_provider=self.pd.export_maintenance_test_recording)
            except (OSError, RuntimeError, ValueError):
                # The normal physical LCD must remain functional even if
                # The chosen interface is unavailable or port 8088 is occupied.
                logging.exception('Remote Display unavailable; continuing with physical LCD')

    def _uart_failed(self):
        self._power_hold_started = None
        if getattr(self, '_boot_active', False):
            self._boot_progress = -1
        if (getattr(self, 'checkkey', None) == self.PowerConfirm
                and getattr(self, '_power_origin', None) == self.MMUMenu):
            self.checkkey = self.MMUMenu
            self._power_origin = None
        if getattr(self, 'checkkey', None) in (self.MMUMenu, self.Tune, self.TuneEdit, self.PrintErrorDetails):
            self._power_focus = False
            self._mmu_canvas_page = None
        self._uart_online = False
        self._uart_epoch += 1
        now = time.monotonic()
        self._next_uart_retry = now + (.15 if now < getattr(self, '_uart_fast_until', 0) else 5)
        self._next_uart_probe = 0
        self._uart_probe_failures = 0
        if self.lcd is not None:
            self.lcd.close()
        self.lcd = None
        probe = getattr(self, '_panel_probe', None)
        if probe is not None:
            probe.close()
            self._panel_probe = None
        logging.warning('LCD UART unavailable; reconnect scheduled')

    def _reset_power_ui(self):
        """A relay cycle starts a new UI session; never replay old input/actions."""
        self.checkkey = self.MainMenu
        self._boot_active = True
        self._boot_connection_started = None
        self._boot_connection_delayed = False
        self._boot_files_started = (None, 0)
        self._boot_progress = -1
        for name in self.SELECTIONS:
            selection = getattr(self, name, None)
            if selection is not None:
                selection.reset()
        self._power_focus = False
        self._power_origin = None
        self._info_scroll = 0
        self._case_light_live_pending = None
        self._case_light_live_refresh = False
        self._case_light_live_epoch = None
        self._case_light_live_future = None
        self._display_selection = 0
        self._display_edit = False
        self._display_save_message = ''
        if hasattr(self, '_display_saved'):
            self._display_values = list(self._display_saved)
        self._mmu_canvas_page = None
        self._mmu_edit = None
        self._mmu_confirmation = None
        self._mmu_map_draft = None
        self._mmu_endless_draft = None
        self._mmu_spool_draft = None
        self._action_feedback = None
        self._stop_waiting = False
        self._pending_start = None
        self._start_error_visible = False
        self._acknowledged_terminal = None
        self.index_prepare = self.index_tune = self.index_control = self.MROWS
        self._live_jog_pending = None
        self._live_jog_future = None
        self._encoder_event = self.ENCODER_DIFF_NO
        self.last_status = None
        self.last_cardpercentValue = 101
        self.next_rts_update_ms = 0

    def _ui_lifecycle(self):
        reader = getattr(self.pd.subscription, 'lifecycle', None)
        if callable(reader):
            value = reader()
            if isinstance(value, dict) and 'epoch' in value:
                return value
        # Test doubles and legacy subscriptions retain their normal snapshot.
        return self.pd.subscription.snapshot()

    def _poll_panel_power(self):
        monitor = getattr(self, '_power_monitor', None)
        if monitor is None:
            return
        status = monitor.poll()
        snapshot = self._ui_lifecycle()
        device = self.pd.power_device.casefold()
        notified = snapshot.get('power_devices', {}).get(device)
        if monitor.available is False:
            notified = None
        serial = snapshot.get('power_off_serial', {}).get(device, 0)
        if (notified in ('on', 'off') and
                (notified != getattr(self, '_power_notification', None)
                 or serial != self._relay_off_serial)):
            status = notified
            monitor.status = notified
            self._power_notification = notified
        epoch = snapshot['epoch']
        event_cycle = serial != self._relay_off_serial
        transition = (status in ('on', 'off') and status != self._relay_status
                      and (status == 'off' or self._relay_status is not None))
        # Klipper's epoch covers cycles missed while its WebSocket was down.
        backend_cycle = (snapshot['state'] == 'ready' and epoch != self._panel_backend_epoch
                         and not getattr(self, '_boot_active', False))
        if event_cycle or transition or backend_cycle:
            probe = getattr(self, '_panel_probe', None)
            if probe is not None:
                probe.close()
                self._panel_probe = None
            self._reset_power_ui()
            if self.lcd is not None:
                self.lcd.close()
                self.lcd = None
            self._uart_online = False
            self._uart_epoch += 1
            self._next_uart_retry = 0
            self._uart_probe_failures = 0
            logging.info('Printer power/session changed; starting fresh panel session')
        self._relay_off_serial = serial
        if status in ('on', 'off'):
            self._relay_status = status
        if snapshot['state'] == 'ready':
            self._panel_backend_epoch = epoch
        if hasattr(self, '_uart_start_signal'):
            available = True if notified in ('on', 'off') else monitor.available
            signal = (('power', serial) if available is True and status == 'on' else
                      ('backend', epoch) if available is False and snapshot['state'] == 'ready' else None)
            if signal != self._uart_start_signal:
                self._uart_start_signal = signal
                if signal is not None and not self._uart_online:
                    self._uart_fast_until = time.monotonic() + 10
                    self._next_uart_retry = 0
                    if hasattr(self, '_loop'):
                        self._loop.set_interval(.05)
                    probe = getattr(self, '_panel_probe', None)
                    if probe is not None:
                        probe.accelerate()

    def _ensure_uart(self):
        if getattr(self, '_relay_status', None) == 'off':
            return False
        if self._uart_online:
            return True
        if self._closed or time.monotonic() < self._next_uart_retry:
            return False
        try:
            options = {}
            if hasattr(self, '_panel_probe'):
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
                if self._panel_probe is None:
                    self._panel_probe = PanelProbe(self._settings[0])
                    if time.monotonic() < self._uart_fast_until:
                        self._panel_probe.accelerate()
                port = self._panel_probe.poll()
                if port is None:
                    return False
                self._panel_probe.close()
                self._panel_probe = None
                options['connected_serial'] = port
            if getattr(self, '_emulator', None) is not None:
                options['packet_observer'] = self._emulator
            if getattr(self, '_boot_active', False):
                options['startup_progress'] = lambda lcd, value: self._draw_boot_progress(value, lcd)
            self.lcd = T5UIC1Display(self._settings[0], handshake_timeout=1.0,
                                 handshake_attempts=1, **options)
            async_flash = (getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH',
                                   None) is True)
            if async_flash:
                # Do not hold the UI owner during Flash reads. The defaults
                # remain usable until the verified panel records arrive.
                if not hasattr(self, '_display_values'):
                    self._display_values = [100, 0, 10]
                    self._display_saved = (100, 0, 10)
                if not hasattr(self, '_buzzer_values'):
                    self._buzzer_values = self._buzzer_saved = BuzzerSettings()
                self._panel_flash_lcd = self.lcd
                if not getattr(self, '_display_load_complete', False):
                    self._display_load_future = self.lcd.begin_flash_read(
                        self.lcd.DISPLAY_SETTINGS_ADDRESS,
                        self.lcd.DISPLAY_SETTINGS_SIZE)
                if not getattr(self, '_buzzer_load_complete', False):
                    self._buzzer_load_future = self.lcd.begin_flash_read(
                        buzzer_control.ADDRESS, buzzer_control.RECORD_SIZE)
                if getattr(self, '_display_save_future', None) is not None:
                    self._display_save_future = None
                    self._display_save_message = 'Not saved. Press to retry'
                if getattr(self, '_buzzer_save_future', None) is not None:
                    self._buzzer_save_future = None
                    self._buzzer_save_error = True
            else:
                if not hasattr(self, '_display_values'):
                    try:
                        values = self.lcd.load_display_settings()
                    except (OSError, TimeoutError, T5UIC1ProtocolError):
                        logging.warning('Unable to read display settings', exc_info=True)
                        values = None
                    if isinstance(values, tuple) and len(values) == 2:
                        values = values + (10,)
                    if not isinstance(values, tuple) or len(values) != 3:
                        values = None
                    self._display_values = list(values or (100, 0, 10))
                    self._display_saved = tuple(values or (100, 0, 10))
                if not hasattr(self, '_buzzer_values'):
                    try:
                        values = self.lcd.load_buzzer_settings()
                    except (OSError, TimeoutError, T5UIC1ProtocolError):
                        logging.warning('Buzzer settings unavailable; sounds disabled')
                        values = None
                    self._buzzer_values = values if isinstance(values, BuzzerSettings) else BuzzerSettings()
                    self._buzzer_saved = self._buzzer_values
            self._display_last_activity = time.monotonic()
            self._display_dimmed = False
            self.lcd.set_backlight(display_settings.raw_brightness(self._display_values[0]))
            self._configure_menus()
            if getattr(self, '_boot_active', False):
                self._draw_boot_progress(70)
            else:
                self.HMI_StartFrame(False)
            if getattr(self, 'checkkey', None) == self.BedMeshScreen:
                self.Draw_Bed_Mesh()
            elif getattr(self, 'checkkey', None) == self.MeshProfiles:
                self.Draw_Mesh_Profiles()
            elif getattr(self, 'checkkey', None) == self.BedMeshMenu:
                self.Draw_Bed_Mesh_Menu()
            if getattr(self, 'checkkey', None) == self.MMUMenu:
                self._mmu_canvas_page = None
                self.Draw_MMU_Menu()
            elif getattr(self, 'checkkey', None) == self.Tune:
                self.Draw_Tune_Menu()
            elif getattr(self, 'checkkey', None) == self.TuneEdit:
                self._focus_edit_draw()
            elif getattr(self, 'checkkey', None) == self.PrintErrorDetails:
                self._focus_error_draw()
            if getattr(self, 'checkkey', None) == self.FilePreview:
                self.Draw_File_Preview()
            if getattr(self, 'checkkey', None) == self.DisplayMenu:
                self.Draw_Display_Menu()
            if getattr(self, 'checkkey', None) == self.MaintenanceMenu:
                self.Draw_Maintenance_Menu()
            if getattr(self, 'checkkey', None) == self.BuzzerMenu:
                self.Draw_Buzzer_Menu()
            if getattr(self, 'checkkey', None) == self.RecoveryScreen:
                self.Clear_Popup_Area()
                self._recovery_render = None
                self.Draw_Recovery()
            self.lcd.update()
            if (self.pd.connection_error and self.checkkey != self.MMUMenu
                    and not getattr(self, '_boot_active', False)):
                self._poll_recovery_ui()
            self._uart_online = True
            if hasattr(self, '_loop'):
                self._loop.set_interval(.5)
            self._uart_epoch += 1
            self._uart_probe_failures = 0
            self._next_uart_probe = time.monotonic() + 2.0
            if getattr(self, '_boot_active', False):
                self._poll_boot()
            logging.info('LCD UART connected; %s', 'boot readiness pending'
                         if getattr(self, '_boot_active', False) else 'current screen restored')
            return True
        except (OSError, TimeoutError):
            self._uart_failed()
            return False

    def _draw_progress_track(self, lcd, x, y, width, value):
        # Text-free managed caps work on panels without opcode 0x08.
        from lcd_resources import ICON_PROGRESS_TRACK, ICON_PROGRESS_FILL
        def capsule(length, color, icon):
            length = min(width, max(8, length))
            show_theme_icon(lcd, self.ICON, icon, x, y)
            if length > 8:
                show_theme_icon(lcd, self.ICON, icon, x + length - 8, y)
                lcd.draw_rectangle(1, color, x + 4, y, x + length - 5, y + 7)
        capsule(width, 0x39C8, ICON_PROGRESS_TRACK)
        filled = max(0, min(width, round(width * value / 100)))
        if filled:
            capsule(filled, 0x063B, ICON_PROGRESS_FILL)

    def _draw_boot_progress(self, value, lcd=None, message=None):
        lcd = self.lcd if lcd is None else lcd
        message = message or {40: 'Preparing display assets', 70: 'Waiting for printer...',
                              80: 'Reading printer status', 90: 'Preparing menus',
                              100: 'Starting interface'}.get(value, 'Starting display')
        message = message[:27]
        value = max(getattr(self, '_boot_progress', -1), min(100, value))
        if (value == getattr(self, '_boot_progress', -1)
                and message == getattr(self, '_boot_message', None)
                and lcd is getattr(self, '_boot_animation_lcd', None)):
            return
        if lcd is getattr(self, '_boot_animation_lcd', None) and getattr(self, '_boot_animation_running', False):
            lcd.configure_animation(0, False, getattr(self, '_boot_animation_active_library', self.ICON), 250, 254, self._boot_animation_x, 320, 10)
        self._boot_progress, self._boot_message = value, message
        # Restore original splash pixels; no solid-color patches over the artwork.
        lcd.copy_cache(0, 16, 284, 255, 344, 16, 284, background=True, enhanced=False)
        self._draw_progress_track(lcd, 24, 292, 224, value)
        x = (272 - (len(message)*8 + 24)) // 2
        lcd.draw_text(False, False, lcd.font8x16, 0xE75E, 0,
                      x+24, 322, message)
        library = getattr(lcd, '_boot_animation_library', self.ICON)
        self._boot_animation_running = value < 100 and library is not None
        if self._boot_animation_running:
            lcd.configure_animation(0, True, library, 250, 254, x, 320, 10)
        self._boot_animation_active_library = library
        self._boot_animation_x, self._boot_animation_lcd = x, lcd
        lcd.update()

    def _poll_boot(self):
        snapshot = self.pd.subscription.snapshot()
        if snapshot['state'] != 'ready':
            self._update_ui_state()
            if not self._poll_recovery_ui():
                kind = getattr(getattr(self.pd, 'recovery', None), 'state', None)
                message = ('Starting Klipper...' if getattr(kind, 'kind', None) == 'startup'
                           else 'Connecting to printer...')
                self._draw_boot_progress(70, message=message)
            return
        self._draw_boot_progress(80)
        self._update_ui_state()
        snapshot = self.pd.subscription.snapshot()
        if (snapshot['state'] != 'ready' or self.pd.connection_error
                or not self.pd.state.ready or self.pd.state.epoch != snapshot['epoch']):
            self._draw_boot_progress(80, message='Waiting for printer data')
            return
        self.pd.prefetch_files()
        epoch, started = getattr(self, '_boot_files_started', (None, 0))
        if epoch != snapshot['epoch']:
            started = time.monotonic()
            self._boot_files_started = (snapshot['epoch'], started)
        if ((self.pd._files_loading is True or self.pd._directory_loading is True)
                and time.monotonic() - started < 5.0):
            self._draw_boot_progress(90, message='Preparing file list')
            return
        self._draw_boot_progress(90)
        self._configure_menus()
        self.pd.mmu_session.update()
        self._draw_boot_progress(100)
        self._boot_active = False
        self._uart_epoch += 1
        self._offline = False
        self._panel_backend_epoch = snapshot['epoch']
        self.HMI_StartFrame(False)
        self._display_last_activity = time.monotonic()
        self.lcd.update()

    def _poll_panel_flash(self):
        """Collect completed Flash futures on the same UART-owning UI thread."""
        if getattr(self, '_panel_flash_lcd', None) is not self.lcd:
            return
        changed = False
        for kind in ('display_load', 'buzzer_load', 'display_save', 'buzzer_save'):
            attr = '_' + kind + '_future'
            future = getattr(self, attr, None)
            if future is None or not future.done():
                continue
            setattr(self, attr, None)
            try:
                raw = future.result()
                if kind == 'display_load':
                    values = display_settings.decode(raw)
                    if isinstance(values, tuple) and len(values) == 2:
                        values = values + (10,)
                    if isinstance(values, tuple) and len(values) == 3:
                        old = self._display_saved
                        if (tuple(self._display_values) == old
                                and not getattr(self, '_display_edit', False)
                                and getattr(self, '_display_save_future', None) is None):
                            self._display_values = list(values)
                            if not getattr(self, '_display_dimmed', False):
                                self.lcd.set_backlight(display_settings.raw_brightness(values[0]))
                        self._display_saved = values
                    self._display_load_complete = True
                elif kind == 'buzzer_load':
                    settings = BuzzerSettings.decode(raw)
                    if isinstance(settings, BuzzerSettings):
                        if (self._buzzer_values == self._buzzer_saved
                                and getattr(self, '_buzzer_save_future', None) is None):
                            self._buzzer_values = settings
                        self._buzzer_saved = settings
                    self._buzzer_load_complete = True
                elif kind == 'display_save':
                    self._display_saved = self._display_save_target
                    self._display_edit = False
                    self._display_save_message = ''
                else:
                    self._buzzer_saved = self._buzzer_save_target
                    self._buzzer_save_error = False
                    self._display_save_message = ''
            except Exception as error:
                if kind == 'display_save':
                    self._display_edit = True
                    self._display_save_message = 'Not saved. Press to retry'
                elif kind == 'buzzer_save':
                    self._buzzer_save_error = True
                    self._display_save_message = 'Not saved. Press to retry'
                else:
                    logging.warning('Could not read panel %s: %s', kind, error)
            changed = True
        if changed:
            if getattr(self, 'checkkey', None) == self.DisplayMenu:
                self.Draw_Display_Menu()
                self.lcd.update()
            elif getattr(self, 'checkkey', None) == self.BuzzerMenu:
                self.Draw_Buzzer_Menu()
                self.lcd.update()

    def _update_ui_state(self):
        if getattr(self, '_tick_active', False) and self._tick_state_update is not None:
            return self._tick_state_update
        changed = self.pd.update_variable()
        self._sync_file_lifecycle()
        if getattr(self, '_tick_active', False):
            self._tick_state_update = changed
        return changed

    def _ui_tick(self):
        self._tick_active = True
        self._tick_state_update = None
        try:
            self._ui_tick_body()
        finally:
            self._tick_active = False
            if any(getattr(getattr(self.pd, name, None), 'pending', False) is True
                   for name in ('maintenance_pulse', 'maintenance_reader')):
                if hasattr(self, '_loop'):
                    self._loop.cap_interval(.1)

    def _ui_tick_body(self):
        # Operation deadlines must not depend on the visible screen or LCD.
        self._maintenance_advanced_this_tick = False
        if any(getattr(getattr(self.pd, name, None), 'pending', False) is True
               for name in ('maintenance_pulse', 'maintenance_reader')):
            self._update_ui_state()
            self._advance_maintenance_operations()
            self._maintenance_advanced_this_tick = True
        self._poll_panel_power()
        self._sync_case_light_tracking()
        if not self._uart_online:
            # Keep status current while the panel is disconnected.
            self._update_ui_state()
            self.pd.bed_mesh.update()
            self.pd.mmu_session.update()
            self._ensure_uart()
            return
        try:
            if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                self.lcd.poll_flash_tasks()
                self._poll_panel_flash()
                if self.lcd.flash_busy() and hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
            if self._power_hold_tick():
                return
            now = time.monotonic()
            incremental_probe = (getattr(self.lcd,
                                          'SUPPORTS_NONBLOCKING_LIVENESS', None) is True)
            if now >= getattr(self, '_next_uart_probe', 0):
                self._next_uart_probe = now + 2.0
                if incremental_probe:
                    self.lcd.begin_liveness_probe(timeout=0.5)
                else:
                    result = self.lcd.handshake(timeout=0.5)
                    if result:
                        self._uart_probe_failures = 0
                    else:
                        self._uart_probe_failures = getattr(self, '_uart_probe_failures', 0) + 1
            if incremental_probe:
                result = self.lcd.poll_liveness_probe()
                if result is True:
                    self._uart_probe_failures = 0
                elif result is False:
                    self._uart_probe_failures = getattr(self, '_uart_probe_failures', 0) + 1
            if getattr(self, '_uart_probe_failures', 0):
                if self._uart_probe_failures >= 2:
                    logging.warning('LCD liveness lost; reconnecting')
                    self._uart_failed()
                    return
            if self._power_popup_tick():
                return
            if getattr(self, '_boot_active', False):
                self._poll_boot()
                return
            if (getattr(self, 'checkkey', None) == self.MMUMenu
                    and getattr(self, '_mmu_page', None) == 'home'):
                view = getattr(self, '_mmu_filament_view', None)
                state = getattr(self, '_mmu_animation_state', None)
                animating = bool(view is not None and state is not None
                                 and view.animating(state, now))
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05 if animating else .5)
                if now < getattr(self, '_mmu_status_at', 0):
                    if animating:
                        self._mmu_animation_tick()
                    return
                self._mmu_status_at = now + .5
            elif getattr(self, 'checkkey', None) == self.FilePreview:
                if not getattr(self, '_pending_start', None) and not getattr(self, '_start_error_visible', False):
                    self._poll_file_preview()
                if not getattr(self, '_pending_start', None) and hasattr(self, '_loop'):
                    active = (not getattr(self, '_start_error_visible', False)
                              and self._preview_epoch == self.pd.state.epoch
                              and self._thumbnail_cache.has_foreground_work(self._preview_cache_key))
                    self._loop.set_interval(.02 if active else .5)
                if time.monotonic() < getattr(self, '_preview_status_at', 0):
                    return
                self._preview_status_at = time.monotonic() + .5
            elif getattr(self, 'checkkey', None) == self.SelectFile:
                self._poll_thumbnail_preload()
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.02 if self._thumbnail_cache.has_work() else .5)
                if time.monotonic() < getattr(self, '_file_status_at', 0):
                    return
                self._file_status_at = time.monotonic() + .5
            elif hasattr(self, '_loop'):
                blink = bool(getattr(self, '_quiet_blinks', {}))
                loading = self.checkkey == self.PrintProcess and hasattr(self, '_thumbnail_cache') and self._thumbnail_cache.has_work()
                self._loop.set_interval(.1 if blink else (.05 if loading else .5))
            if getattr(self, '_mesh_pending_points', None) is not None:
                if self.checkkey == self.BedMeshScreen:
                    if hasattr(self, '_loop'):
                        self._loop.set_interval(.02)
                    self._advance_mesh_render()
                else:
                    self._mesh_pending_points = None
            if incremental_probe and getattr(self.lcd, '_liveness_deadline', None) is not None:
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
            self._display_idle_tick()
            if self._draw_header_clock():
                self.lcd.update()
            self.EachMomentUpdate()
        except OSError:
            if self.lcd is not None and g…47478 tokens truncated…iles, paths, keys = self._read('files', prepare,
                    (self.state.epoch, revision, self.file_sort_revision))
                self.files = files
                self._files_paths_snapshot = paths
                self._file_thumbnail_keys = keys
                self._file_thumbnail_list = files
                self.file_error = None
                self._files_loaded = True
                self._files_loading = False
                self._file_retry_at = 0.0
            except ReadPending:
                pass
            except (MoonrakerError, KeyError, TypeError, ValueError) as exc:
                self.file_error = str(exc)
                self._files_loaded = False
                self._files_loading = False
                self._file_retry_at = time.monotonic() + 5
        return getattr(self, '_files_paths_snapshot', tuple())

    def prefetch_files(self):
        """Warm the root browser cache using the existing nonblocking read worker."""
        if not self.state.ready:
            return
        key = (self.state.epoch, self.state.file_revision, '')
        if not self._files_loaded or key not in self._directory_cache:
            self.GetDirectory('')

    DIRECTORY_CACHE_BYTES = 2 * 1024 * 1024

    @staticmethod
    def _directory_size(entries):
        # Include Python container/string overhead, not just serialized JSON bytes.
        pending = [entries]
        size = 0
        while pending:
            value = pending.pop()
            size += sys.getsizeof(value)
            if isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, (list, tuple)):
                pending.extend(value)
        return size

    def GetDirectory(self, directory=''):
        self._directory_loading = False
        self.GetFiles()
        if self.file_error or self._files_loading:
            return ()
        if directory and any(part in ('', '.', '..') for part in directory.split('/')):
            raise ValueError('Invalid directory path')
        key = (self.state.epoch, self.state.file_revision, directory)
        orders = getattr(self, '_directory_orders', {})
        self._directory_orders = orders
        sizes = getattr(self, '_directory_cache_sizes', {})
        self._directory_cache_sizes = sizes
        for old in tuple(sizes):
            if old not in self._directory_cache:
                del sizes[old]
                orders.pop(old, None)
        if self._directory_revision_key != key[:2]:
            self._directory_cache.clear()
            sizes.clear()
            orders.clear()
            self._directory_retry_at.clear()
            self._directory_revision_key = key[:2]
        try:
            if key not in self._directory_cache:
                if time.monotonic() < self._directory_retry_at.get(key, 0):
                    return ()
                self._directory_loading = True
                preference = self.file_sort
                def prepare_directory():
                    data = self.getREST('/server/files/directory?path=' + quote('gcodes/' + directory, safe=''))['result']
                    entries = []
                    for group, name_key, is_dir in (('dirs', 'dirname', True), ('files', 'filename', False)):
                        for item in data[group]:
                            name = item[name_key]
                            if not isinstance(name, str) or not name or '/' in name or name in ('.', '..'):
                                raise ValueError('Invalid directory entry')
                            if name.startswith('.') or (not is_dir and not name.lower().endswith('.gcode')):
                                continue
                            path = (directory + '/' if directory else '') + name
                            entries.append(dict(item, path=path + ('/' if is_dir else ''), isDirectory=is_dir))
                    if len({item['path'] for item in entries}) != len(entries):
                        raise ValueError('Duplicate directory entries')
                    size = self._directory_size(entries)
                    self._sort_files(entries, preference=preference)
                    entries.sort(key=lambda item: not item['isDirectory'])
                    return entries, size, tuple(item['path'] for item in entries)
                entries, size, paths = self._read(('directory', directory), prepare_directory,
                    (key, preference))
                if size <= self.DIRECTORY_CACHE_BYTES:
                    self._directory_cache[key] = entries
                    sizes[key] = size
                    orders[key] = (preference, paths)
                self._directory_loading = False
                self._directory_retry_at.pop(key, None)
            # Insertion-ordered cache: keep the root and current parent available
            # while bounding memory during long sessions with many folders.
            if key in self._directory_cache:
                entries = self._directory_cache.pop(key)
                self._directory_cache[key] = entries
            parent = directory.rpartition('/')[0]
            retained = sum(sizes.values())
            while len(self._directory_cache) > 64 or retained > self.DIRECTORY_CACHE_BYTES:
                victim = next((k for k in self._directory_cache
                               if k[2] not in ('', directory, parent)), None)
                if victim is None:
                    # Byte limit wins even when only root/current/parent remain.
                    victim = next(iter(self._directory_cache))
                del self._directory_cache[victim]
                retained -= sizes.pop(victim, 0)
                orders.pop(victim, None)
            order = orders.get(key)
            if order is not None and order[0] != self.file_sort:
                preference = self.file_sort
                source = entries
                def resort():
                    items = list(source)
                    self._sort_files(items, preference=preference)
                    items.sort(key=lambda item: not item['isDirectory'])
                    return items, tuple(item['path'] for item in items)
                self._directory_loading = True
                entries, paths = self._read(('directory_sort', directory), resort, (key, preference))
                self._directory_loading = False
                self._directory_cache[key] = entries
                orders[key] = (preference, paths)
            return orders[key][1] if key in orders else paths
        except ReadPending:
            return ()
        except (MoonrakerError, KeyError, TypeError, ValueError) as error:
            self._directory_loading = False
            self._directory_retry_at[key] = time.monotonic() + 5
            # Only the newest retry deadlines may survive in the current revision.
            for old in list(self._directory_retry_at)[:-64]:
                del self._directory_retry_at[old]
            self.file_error = str(error)
            self._files_loaded = False
            return ()

    @staticmethod
    def _spool_remaining_percent(spool):
        try:
            remaining = float(spool['remaining_weight'])
            initial = float(spool.get('initial_weight') or 0)
            if initial <= 0:
                used = float(spool.get('used_weight') or 0)
                initial = remaining + used
            if (not math.isfinite(remaining) or not math.isfinite(initial)
                    or initial <= 0 or remaining < 0):
                return None
            return max(0, min(100, int(round(remaining * 100.0 / initial))))
        except (KeyError, TypeError, ValueError):
            return None

    def _poll_spoolman_percentages(self, spool_ids):
        now = time.monotonic()
        changed = False
        valid_ids = {int(sid) for sid in spool_ids
                     if isinstance(sid, (int, float)) and int(sid) > 0}

        for sid, future in list(self._spoolman_futures.items()):
            if not future.done():
                continue
            del self._spoolman_futures[sid]
            self._spoolman_refresh_at[sid] = now + 15.0
            try:
                response = future.result()
                spool = response['result']
                percent = self._spool_remaining_percent(spool)
            except (KeyError, TypeError, ValueError, MoonrakerError):
                percent = None
            if percent is None:
                # Never present an old percentage as current after a failed refresh.
                if sid in self._spoolman_percentages:
                    del self._spoolman_percentages[sid]
                    changed = True
            elif self._spoolman_percentages.get(sid) != percent:
                self._spoolman_percentages[sid] = percent
                changed = True

        for sid in list(self._spoolman_percentages):
            if sid not in valid_ids:
                del self._spoolman_percentages[sid]
                changed = True
        for sid in list(self._spoolman_refresh_at):
            if sid not in valid_ids:
                del self._spoolman_refresh_at[sid]

        for sid in valid_ids:
            if sid in self._spoolman_futures or now < self._spoolman_refresh_at.get(sid, 0):
                continue
            self._spoolman_futures[sid] = self.spoolman_client.post(
                '/server/spoolman/proxy',
                {'request_method': 'GET', 'path': '/v1/spool/%d' % sid},
                report_error=False)
        return changed

    def update_variable(self):
        self.check_command_results()
        if self._settings_save is not None and self._settings_save.done():
            try:
                self._settings_save.result()
                self._preset_baseline = self._preset_saved_signature
                self._preset_original = self._preset_save_original
                self.settings_error = None
            except Exception as error:
                self.settings_error = str(error)
            self._settings_save = None
            self._preset_refresh_at = 0.0
        presets_changed = self.refresh_mainsail_presets()
        sort_changed = self.refresh_file_sort() if self._files_loaded else False
        try:
            # Effective Klipper config stays stable within a websocket epoch.
            # Avoid copying and recursively freezing the entire settings tree
            # on every status revision; status itself remains freshly copied.
            lifecycle_reader = getattr(self.subscription,'lifecycle',None)
            life = lifecycle_reader() if callable(lifecycle_reader) else None
            same_revision = (isinstance(life,dict) and self.state.ready
                             and life.get('state') == 'ready'
                             and life.get('epoch') == self.state.epoch
                             and life.get('revision') == self.state.revision)
            if same_revision:
                state = replace(self.state, file_revision=life.get('file_revision',self.state.file_revision))
            elif getattr(self.subscription, '_supports_settings_elision', None) is True:
                snap = self.subscription.snapshot(include_settings=False)
                reuse = self.state.ready and snap['epoch'] == self.state.epoch
                if not reuse: snap = self.subscription.snapshot()
                state = PrinterState.from_snapshot(snap,reused_settings=self.state.settings if reuse else None)
            else:
                state = PrinterState.from_snapshot(self.subscription.snapshot())
            if not state.ready:
                if self.state.ready:
                    self.maintenance_pulse.cancel()
                    self.maintenance_reader.cancel()
                    self.maintenance.clear()
                if self.state.ready or self.files or self._files_loaded:
                    self._invalidate_files()
                self.state = state
                self._note_maintenance_state(state)
                self._files_loaded = False
                self.connection_error = state.error or 'Klipper is not ready'
                return False
            data = state.status
            th = state.status['toolhead']
            caps_key = (state.epoch,id(state.settings),state.objects,th.get('extruder'),
                        tuple(th.get('axis_minimum',())),tuple(th.get('axis_maximum',())))
            caps = (self.capabilities if caps_key == getattr(self,'_caps_cache_key',None)
                    else PrinterCapabilities.from_state(state))
            gcm = data['gcode_move']
            toolhead = data['toolhead']
            # Validate required fields before committing the snapshot.
            job = {'virtual_sdcard': data['virtual_sdcard'], 'print_stats': data['print_stats']}
            print_state = job['print_stats']['state']
            def finite_coordinates(values, count, label):
                if (not isinstance(values, (list, tuple)) or len(values) < count
                        or any(isinstance(v, bool) for v in values[:count])):
                    raise ValueError('Invalid ' + label)
                result = tuple(float(v) for v in values[:count])
                if not all(math.isfinite(v) for v in result):
                    raise ValueError('Invalid ' + label)
                return result
            position = finite_coordinates(toolhead['position'], 4, 'toolhead position')
            x, y, z, e = position
            finite_coordinates(gcm.get('position', position), 4, 'command position')
            origin = finite_coordinates(gcm['homing_origin'], 3, 'homing origin')[2]
            absolute_moves = gcm['absolute_coordinates']
            absolute_extrude = gcm['absolute_extrude']
            speed_percent = float(gcm.get('speed_factor', 1.0)) * 100
            flow_percent = float(gcm.get('extrude_factor', 1.0)) * 100
            if not math.isfinite(speed_percent) or speed_percent <= 0:
                raise ValueError('Invalid feedrate percentage')
            if not math.isfinite(flow_percent) or flow_percent <= 0:
                raise ValueError('Invalid flow percentage')
            motion = data.get('motion_report', {})
            live_position = motion.get('live_position', position)
            if not isinstance(live_position, (list, tuple)) or len(live_position) < 3:
                raise ValueError('Invalid live position')
            live_xyz = tuple(float(value) for value in live_position[:3])
            live_velocity = float(motion.get('live_velocity', 0.0))
            live_extruder_velocity = float(motion.get('live_extruder_velocity', 0.0))
            if (not all(math.isfinite(value) for value in live_xyz)
                    or not math.isfinite(live_velocity)
                    or not math.isfinite(live_extruder_velocity)):
                raise ValueError('Invalid live motion telemetry')
            hotend_settings = state.settings.get(caps.active_hotend.name, {}) if caps.active_hotend else {}
            filament_diameter = float(hotend_settings.get('filament_diameter', 1.75))
            if not math.isfinite(filament_diameter) or filament_diameter <= 0:
                raise ValueError('Invalid filament diameter')
            filament_area = math.pi * (filament_diameter * 0.5) ** 2
            volumetric_flow = live_extruder_velocity * filament_area
            thermal = copy.deepcopy(self.thermalManager)
            for obj, target in [(caps.active_hotend.name if caps.active_hotend else None, thermal['temp_hotend'][0]),
                                ('heater_bed' if caps.bed else None, thermal['temp_bed'])]:
                if obj is None:
                    target['celsius'] = target['target'] = 0
                else:
                    target['celsius'] = int(data[obj]['temperature'])
                    target['target'] = int(data[obj]['target'])
            thermal['fan_speed'][0] = int(data['fan']['speed'] * 100) if caps.fan else 0
            mmu = None
            spoolman_changed = False
            if 'mmu' in data:
                try:
                    raw_mmu = data['mmu']
                    num_gates = int(raw_mmu.get('num_gates', 0))
                    gate = int(raw_mmu.get('gate', -1))
                    colors = raw_mmu.get('gate_color_rgb', [])
                    statuses = raw_mmu.get('gate_status', [])
                    spool_ids = tuple(raw_mmu.get('gate_spool_id', [])[:num_gates])
                    spoolman_changed = self._poll_spoolman_percentages(spool_ids)
                    if num_gates < 1 or len(colors) < num_gates or len(statuses) < num_gates:
                        raise ValueError('Invalid MMU status')
                    normalized_colors = []
                    for color in colors[:num_gates]:
                        if (not isinstance(color, (list, tuple)) or len(color) != 3
                                or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                           for value in color)):
                            raise ValueError('Invalid MMU gate color')
                        # Happy Hare publishes gate_color_rgb as normalized RGB floats.
                        normalized_colors.append(tuple(max(0.0, min(1.0, float(value)))
                                                       for value in color))
                    unit_name = 'MMU'
                    machine = data.get('mmu_machine', {})
                    # Happy Hare reports the selected unit as "unit" on current
                    # releases and "unit_selected" on older controller status.
                    unit_index = int(raw_mmu.get('unit',
                                                 raw_mmu.get('unit_selected', 0)))
                    unit_info = machine.get('unit_%d' % unit_index, {})
                    if isinstance(unit_info, Mapping):
                        unit_name = str(unit_info.get('display_name') or
                                        unit_info.get('name') or 'MMU')
                    exit_led_object = 'unit%d_mmu_exit_leds' % unit_index
                    exit_led_data = data.get(exit_led_object, {}).get('color_data', ())
                    exit_led_rgb = ()
                    if len(exit_led_data) >= num_gates:
                        normalized_leds = []
                        for led_color in exit_led_data[:num_gates]:
                            if (not isinstance(led_color, (list, tuple)) or len(led_color) < 3
                                    or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                               for value in led_color[:3])):
                                normalized_leds = []
                                break
                            normalized_leds.append(tuple(max(0.0, min(1.0, float(value)))
                                                         for value in led_color[:3]))
                        exit_led_rgb = tuple(normalized_leds)
                    mmu = {'num_gates': num_gates, 'gate': gate,
                           'gate_status': tuple(int(value) for value in statuses[:num_gates]),
                           'gate_color_rgb': tuple(normalized_colors),
                           'gate_spool_id': spool_ids,
                           'remaining_percent': tuple(
                               self._spoolman_percentages.get(int(sid))
                               if isinstance(sid, (int, float)) and int(sid) > 0 else None
                               for sid in spool_ids),
                           'exit_led_rgb': exit_led_rgb,
                           'name': unit_name,
                           'filament': str(raw_mmu.get('filament', 'Unknown'))}
                except (KeyError, TypeError, IndexError, ValueError, OverflowError) as exc:
                    # Optional MMU telemetry must not make the core printer UI offline.
                    logging.warning('Ignoring invalid MMU status: %s', exc)
                    mmu = None
                    spoolman_changed = False
        except (MoonrakerError, KeyError, TypeError, IndexError, ValueError) as exc:
            self.connection_error = str(exc)
            return False
        self.connection_error = None
        changed = state != self.state or spoolman_changed or presets_changed or sort_changed
        self.state = state
        self._note_maintenance_state(state)
        self.capabilities = caps
        self._caps_cache_key = caps_key
        self._apply_capabilities(caps)
        self.SHORT_BUILD_VERSION = state.software_version
        if state.epoch != self._file_epoch:
            self.maintenance_pulse.cancel()
            self.maintenance_reader.cancel()
            # Reuse the existing Klipper READY epoch transition. Never
            # rediscover on menu entry or during ordinary print updates.
            self.maintenance.ready(state, self.client, self._maintenance_worker,
                                   lambda: self.state, integrations=self.maintenance_integrations(state))
            self._invalidate_files()
            self._file_epoch = state.epoch
        if state.file_revision != self._file_revision:
            self._files_loaded = False
            self._file_revision = state.file_revision
        self.thermalManager = thermal
        self.feedrate_percentage = round(speed_percent)
        self.flow_percentage = round(flow_percent)
        self.live_velocity = live_velocity
        self.live_extruder_velocity = live_extruder_velocity
        self.volumetric_flow = volumetric_flow
        self.live_position = live_xyz
        self.dashboard_fan_pwm = round(data['fan']['speed'] * 255) if caps.fan else 0
        self.mmu = mmu
        self.absolute_moves = absolute_moves
        self.absolute_extrude = absolute_extrude
        self.current_position.x, self.current_position.y, self.current_position.z, self.current_position.e = x, y, z, e
        homed = toolhead.get('homed_axes', '')
        self.current_position.home_x = 'x' in homed
        self.current_position.home_y = 'y' in homed
        self.current_position.home_z = 'z' in homed
        self.BABY_Z_VAR = origin
        self.HMI_ValueStruct.offset_value = origin * 100
        self.job_Info = job
        self.file_name = job['print_stats'].get('filename', '')
        self.status = print_state
        self._refresh_print_metadata()
        self.HMI_flag.print_finish = print_state == 'complete'
        return changed

    def printingIsPaused(self):
        return self.job_Info['print_stats']['state'] == "paused" or self.job_Info['print_stats']['state'] == "pausing"

    def _print_file_identity(self, filename):
        reader = getattr(self.subscription, 'file_identity', None)
        identity = reader(filename) if callable(reader) else None
        return identity if isinstance(identity, tuple) and len(identity) == 2 else (self.state.epoch, self.state.file_revision)

    def _refresh_print_metadata(self):
        """One bounded asynchronous metadata read per job/file revision."""
        filename = self.job_Info['print_stats'].get('filename', '')
        stamp = (*self._print_file_identity(filename), filename)
        if stamp != getattr(self, '_print_metadata_stamp', None):
            old = getattr(self, '_print_metadata_stamp', None)
            self._print_metadata_stamp = stamp
            if old is None or old[0] != stamp[0] or old[2] != filename:
                self._print_metadata = {}
            self._print_metadata_loaded = False
            self._print_metadata_retry = 0.
            job = self._read_jobs.pop('print_metadata', None)
            if job is not None:
                job[1].cancel()
        if (not filename or self.job_Info['print_stats']['state'] == 'standby'
                or self._print_metadata_loaded or time.monotonic() < self._print_metadata_retry):
            return
        try:
            response = self._read('print_metadata', lambda: self.getREST(
                '/server/files/metadata?filename=' + quote(filename, safe='')), stamp)
            metadata = response.get('result') if isinstance(response, Mapping) else None
            if not isinstance(metadata, Mapping):
                raise ValueError('Invalid print metadata')
            self._print_metadata = {key: time_number(metadata.get(key)) for key in
                                    ('gcode_start_byte', 'gcode_end_byte',
                                     'filament_total', 'estimated_time')}
            self._print_metadata_loaded = True
        except ReadPending:
            pass
        except Exception as error:
            logging.debug('Print time metadata unavailable: %s', error)
            self._print_metadata_retry = time.monotonic() + 10.

    def _current_print_metadata(self):
        stamp = getattr(self, '_print_metadata_stamp', None)
        filename = self.job_Info['print_stats'].get('filename', '')
        if stamp is None or stamp[2] != filename:
            return {}
        state = getattr(self, 'state', None)
        if state is not None and stamp[0] != state.epoch:
            return {}
        return getattr(self, '_print_metadata', {})

    def getPercent(self):
        if self.job_Info['print_stats']['state'] == 'standby':
            return 0
        return 100 * print_progress(self.job_Info['virtual_sdcard'], self._current_print_metadata())

    def duration(self):
        stats = self.job_Info['print_stats']
        if stats['state'] == 'standby':
            return 0
        total = time_number(stats.get('total_duration'))
        return total if total is not None else (time_number(stats.get('print_duration')) or 0)

    def print_time_estimates(self):
        return print_estimates(self.job_Info['print_stats'], self.job_Info['virtual_sdcard'],
                               self._current_print_metadata())

    def remain(self):
        return self.print_time_estimates()[0] or 0

    def openAndPrintFile(self, path):
        if self.maintenance_pulse.pending:
            raise ValueError('Wait for Maintenance pulse to finish')
        if self.jog_recovery_required:
            raise ValueError('Restore jog state before starting a print')
        if (not isinstance(path, str) or not self._files_loaded or self.file_error
                or path not in {item['path'] for item in self.files}):
            raise ValueError('Selected file is no longer available')
        if self.status in ('printing', 'paused', 'pausing'):
            raise ValueError('A print is already active')
        return self.postREST('/printer/print/start', json={'filename': path})

    def cancel_job(self):
        """Submit cancellation over WebSocket; retain real RPC errors.

        The response can be delayed by blocking Klipper macros.  HTTP's
        five-second timeout would incorrectly report a submitted cancel as
        failed, potentially prompting an unsafe duplicate request.
        """
        snapshot = self.subscription.snapshot()
        if (self.connection_error or not self.state.ready
                or snapshot['state'] != 'ready'
                or snapshot['epoch'] != self.state.epoch):
            future = Future()
            future.set_exception(MoonrakerError('Printer connection is not ready'))
            return future
        epoch = snapshot['epoch']
        filename = snapshot['status'].get('print_stats', {}).get('filename')

        def still_same_job():
            current = self.subscription.snapshot()
            stats = current['status'].get('print_stats', {})
            return (current['state'] == 'ready' and current['epoch'] == epoch
                    and stats.get('filename') == filename
                    and stats.get('state') in ('printing', 'paused', 'pausing'))

        return self.subscription.request('printer.print.cancel', guard=still_same_job)

    def pause_job(self, report_error=True): #fixed
        return self.postREST('/printer/print/pause', json=None, **({} if report_error else {'report_error': False}))

    def resume_job(self, report_error=True): #fixed
        if self.jog_recovery_required:
            raise ValueError('Restore jog state before resuming')
        return self.postREST('/printer/print/resume', json=None, **({} if report_error else {'report_error': False}))

    def print_settings(self):
        from print_tuning import settings
        return settings(self)

    def set_print_setting(self, key, value, report_error=True):
        from print_tuning import set_value
        return set_value(self, key, value, report_error=report_error)

    def print_layers(self):
        from print_tuning import layers
        return layers(self)

    def set_feedrate(self, fr, report_error=True):
        fr = float(fr)
        if not math.isfinite(fr) or fr <= 0:
            raise ValueError('Feedrate percentage must be positive')
        send = self.sendGCode if report_error else lambda script: self.sendGCode(script, report_error=False)
        return send('M220 S{:g}'.format(fr))

    def motion_settings(self):
        if not self.state.ready:
            return ()
        toolhead = self.state.status.get('toolhead', {})
        available = []
        for field, argument, label, step in PARAMETERS:
            if field in toolhead:
                try:
                    value = validate_motion(field, toolhead[field])
                except (TypeError, ValueError):
                    continue
                available.append((field, argument, label, step, value))
        return tuple(available)

    def set_motion_limit(self, field, value, report_error=True):
        setting = next((item for item in self.motion_settings() if item[0] == field), None)
        if setting is None:
            raise ValueError('Motion setting is unavailable')
        value = validate_motion(field, value)
        send = self.sendGCode if report_error else lambda script: self.sendGCode(script, report_error=False)
        return send('SET_VELOCITY_LIMIT {}={:g}'.format(setting[1], value))

    def home(self, homeZ=False): #fixed using gcode
        script = 'G28 X Y'
        if homeZ:
            script += (' Z')
        return self.sendGCode(script)

    def _jog(self, axis, value, speed, absolute):
        if self.jog_recovery_required:
            raise ValueError('Restore the preceding jog state before moving')
        axis = str(axis).upper()
        if axis not in ('X', 'Y', 'Z', 'E'):
            raise ValueError('Invalid jog axis')
        value, speed = float(value), float(speed)
        if not math.isfinite(value) or not math.isfinite(speed) or speed <= 0:
            raise ValueError('Invalid jog value or speed')
        snapshot = self.subscription.snapshot()
        state = PrinterState.from_snapshot(snapshot)
        if not state.ready or self.connection_error:
            raise ValueError('Printer is unavailable')
        if state.status['print_stats']['state'] in ('printing', 'paused', 'pausing'):
            raise ValueError('Jogging is unavailable during a print')
        caps = PrinterCapabilities.from_state(state)
        toolhead = state.status['toolhead']
        # Use command-space position before transforms such as bed mesh.
        position = state.status['gcode_move']['position']
        index = 'XYZE'.index(axis)
        current = float(position[index])
        if not math.isfinite(current):
            raise ValueError('Invalid printer position')
        delta = value - current if absolute else value
        target = current + delta
        if axis == 'E':
            heater = caps.active_hotend
            if heater is None or not state.status.get(heater.name, {}).get('can_extrude', False):
                raise ValueError('Extruder is unavailable or too cold')
            if abs(delta) > heater.max_extrude_distance:
                raise ValueError('Extrusion exceeds configured distance')
        else:
            if axis.lower() not in toolhead.get('homed_axes', ''):
                raise ValueError('Axis must be homed before jogging')
            if not caps.axis_minimum[index] <= target <= caps.axis_maximum[index]:
                raise ValueError('Jog exceeds configured axis range')
        max_velocity = float(toolhead['max_velocity'])
        if axis == 'Z':
            max_velocity = min(max_velocity, float(state.settings.get('printer', {}).get('max_z_velocity', max_velocity)))
        if not math.isfinite(max_velocity) or max_velocity <= 0:
            raise ValueError('Invalid configured velocity')
        speed = min(speed, max_velocity * 60)
        if delta == 0:
            return None
        # Klipper saves/restores feed and extrusion factors as well as G90/M82.
        # Relative displacement avoids changing the G92/work origin.
        name = self._jog_state_name
        restore = 'RESTORE_GCODE_STATE NAME={} MOVE=0'.format(name)
        script = '\n'.join(('SAVE_GCODE_STATE NAME=' + name, 'G91', 'M83',
                            'M220 S100', 'M221 S100',
                            'G1 {}{:g} F{:g}'.format(axis, delta, speed), restore))
        with self._jog_lock:
            self._jog_restore = restore
        try:
            dispatch_guard = motion_dispatch_guard(self, owner='jog', position=True,
                                                   extrusion=heater.name if axis == 'E' else None, initial=snapshot)
            future = self.sendGCode(script, cleanup=restore, report_error=False, dispatch_guard=dispatch_guard)
        except Exception:
            # Submission failed before sending anything.
            with self._jog_lock:
                self._jog_restore = None
            raise
        if isinstance(future, Future):
            future.add_done_callback(lambda done: self._jog_finished(done, restore))
        return future

    @property
    def jog_recovery_required(self):
        with self._jog_lock:
            return self._jog_restore is not None

    def _jog_finished(self, future, restore):
        if future.cancelled() or getattr(future, 'cleanup_complete', False):
            with self._jog_lock:
                if self._jog_restore == restore:
                    self._jog_restore = None

    def restore_jog_state(self):
        with self._jog_lock:
            restore = self._jog_restore
        if restore is None:
            raise ValueError('No jog state needs recovery')
        if self.status in ('printing', 'paused', 'pausing'):
            raise ValueError('Stop the print before restoring jog state')
        future = self.postREST('/printer/gcode/script', json={'script': restore})
        def recovered(done):
            if not done.cancelled() and done.exception() is None:
                self._jog_finished(done, restore)
        future.add_done_callback(recovered)
        return future

    def moveRelative(self, axis, distance, speed):
        return self._jog(axis, distance, speed, False)

    def moveAbsolute(self, axis, position, speed):
        return self._jog(axis, position, speed, True)

    def clear_gcode_responses(self):
        from queue import Empty
        while True:
            try:
                self.subscription.gcode_responses.get_nowait()
            except Empty:
                return

    def pop_gcode_response(self):
        from queue import Empty
        try:
            return self.subscription.gcode_responses.get_nowait()
        except Empty:
            return None

    def case_light_state(self):
        snapshot = self.subscription.snapshot()
        value = snapshot['status'].get('output_pin case_light', {}).get('value')
        if snapshot['state'] != 'ready' or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(value) or not 0 <= value <= 1:
            return None
        return value > 0, int(round(value * 100))

    def set_case_light_brightness(self, percent):
        percent = float(percent)
        snapshot = self.subscription.snapshot()
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError('Case light brightness out of range')
        if 'output_pin case_light' not in snapshot['objects']:
            raise ValueError('Case light output pin unavailable')
        settings = snapshot['settings'].get('output_pin case_light', {})
        if str(settings.get('pwm', False)).lower() not in ('true', '1'):
            if percent not in (0, 100):
                raise ValueError('Digital case light supports only on/off')
            return self.sendGCodeObserved('SET_PIN PIN=case_light VALUE={:.6f}'.format(percent / 100))
        scale = float(settings.get('scale', 1))
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid case light scale')
        return self.sendGCodeObserved('SET_PIN PIN=case_light VALUE={:.6f}'.format(percent * scale / 100))

    def sendGCodeObserved(self, gcode):
        """Dispatch long-running G-Code without waiting for its completion response.

        The returned Future completes when the JSON-RPC notification is written to the
        live Moonraker WebSocket. Physical completion must be confirmed from subscribed
        printer state by the caller.
        """
        snapshot = self.subscription.snapshot()
        if (self.connection_error or not self.state.ready or snapshot['state'] != 'ready'
                or snapshot['epoch'] != self.state.epoch):
            future = Future()
            future.set_exception(MoonrakerError('Printer connection is not ready'))
            return future
        if self.jog_recovery_required:
            raise ValueError('Restore jog state before sending motion commands')
        guard = motion_dispatch_guard(self) if gcode.strip() == 'G28' else None
        if gcode.strip() == 'G28':
            return self.subscription.request('printer.gcode.script', {'script': gcode + '\nM400'}, guard=guard)
        return self.subscription.notify('printer.gcode.script', {'script': gcode}, guard=guard)

    def sendGCode(self, gcode, cleanup=None, report_error=True, dispatch_guard=None):
        if cleanup is None and self.jog_recovery_required:
            # Heater/fan shutdown and temperature control do not depend on modes.
            allowed = {'TURN_OFF_HEATERS', 'SET_HEATER_TEMPERATURE', 'M106', 'M107'}
            if any(line.strip().split()[0].upper() not in allowed
                   for line in gcode.splitlines() if line.strip()):
                raise ValueError('Restore jog state before sending motion commands')
        if dispatch_guard is None and gcode.strip() in ('G28', 'G28 X Y', 'G28 X Y Z', 'M84'):
            dispatch_guard = motion_dispatch_guard(self)
        if cleanup is not None and gcode.startswith('SAVE_GCODE_STATE NAME=LCD_PROBE_CENTER\n'):
            return self.subscription.request_script_with_cleanup(gcode, cleanup, dispatch_guard)
        if cleanup is not None:
            return self.postREST('/printer/gcode/script', json={'script': gcode},
                                 cleanup={'script': cleanup}, report_error=report_error, dispatch_guard=dispatch_guard)
        return self.postREST('/printer/gcode/script', json={'script': gcode},
                             report_error=report_error, dispatch_guard=dispatch_guard)

    def disable_all_heaters(self):
        if not self.capabilities.has_heaters:
            return None
        return self.sendGCode('TURN_OFF_HEATERS')

    def cooldown(self):
        commands = []
        if self.capabilities.has_heaters:
            commands.append('TURN_OFF_HEATERS')
        if self.capabilities.fan:
            commands.append(self._fan_command(0))
        if commands:
            return self.sendGCode('\n'.join(commands))

    def zero_fan_speeds(self):
        if self.HAS_FAN:
            return self.setFanSpeed(0)

    @staticmethod
    def _fan_command(percent):
        percent = float(percent)
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError('Fan speed is out of range')
        return 'M106 S{:g}'.format(percent * 255 / 100)

    def setFanSpeed(self, percent, report_error=True):
        if not self.HAS_FAN:
            raise ValueError('Fan is unavailable')
        send = self.sendGCode if report_error else lambda script: self.sendGCode(script, report_error=False)
        return send(self._fan_command(percent))

    def preheat(self, profile):
        preset = next((item for item in self.material_preset if item.name == profile), None)
        if preset is None:
            raise ValueError('Unknown preheat profile')
        return self.preHeat(preset.bed_temp, preset.hotend_temp)

    def preheat_preset(self, index):
        if not isinstance(index, int) or not 0 <= index < len(self.material_preset):
            raise ValueError('Unknown preheat preset')
        preset = self.material_preset[index]
        return self.preHeat(preset.bed_temp, preset.hotend_temp)

    def discard_preset_edits(self, profile):
        if self._settings_save is not None:
            raise ValueError('Wait for preset save before discarding edits')
        if not 0 <= profile < len(self._preset_original):
            raise ValueError('Preset is no longer available')
        self.material_preset[profile] = copy.deepcopy(self._preset_original[profile])
        self._preset_refresh_at = 0.0

    def save_settings(self):
        if self.presets_from_mainsail:
            if self._settings_save is not None and not self._settings_save.done():
                return self._settings_save
            writes = []
            for preset in self.material_preset:
                if not preset.mainsail_id or not isinstance(preset.mainsail_raw, Mapping):
                    raise ValueError('Mainsail preset metadata is unavailable')
                raw = copy.deepcopy(preset.mainsail_raw)
                raw['name'] = preset.name
                values = raw.setdefault('values', {})
                for device, target in (('extruder', preset.hotend_temp), ('heater_bed', preset.bed_temp)):
                    if isinstance(values.get(device), Mapping):
                        values[device] = dict(values[device], value=target)
                writes.append({'namespace': 'mainsail', 'key': 'presets.presets.' + preset.mainsail_id, 'value': raw})
            def save():
                for payload in writes:
                    self.client.post('/server/database/item', payload).result(timeout=self.client.timeout + 1)
                return True
            self._preset_save_original = copy.deepcopy(self.material_preset)
            self._preset_saved_signature = self._preset_signature(self.material_preset)
            self._settings_save = self._read_worker.submit(save)
            return self._settings_save
        try:
            self.preset_store.save([vars(preset).copy() for preset in self.material_preset])
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            self.settings_error = str(error)
            logging.error('Cannot save presets to %s: %s', self.preset_store.path, error)
            return False
        self._preset_original = copy.deepcopy(self.material_preset)
        self.settings_error = None
        return True

    def setExtTemp(self, target, toolnum=None, report_error=True):
        heater = self.capabilities.active_hotend
        if toolnum is not None:
            name = 'extruder' + (str(toolnum) if toolnum else '')
            heater = next((item for item in self.capabilities.hotends if item.name == name), None)
        if heater is None:
            raise ValueError('Hotend is unavailable')
        value = heater.validate_target(target)
        send = self.sendGCode if report_error else lambda script: self.sendGCode(script, report_error=False)
        return send('SET_HEATER_TEMPERATURE HEATER={} TARGET={:g}'.format(heater.name, value))

    def setBedTemp(self, target, report_error=True):
        heater = self.capabilities.bed
        if heater is None:
            raise ValueError('Heated bed is unavailable')
        value = heater.validate_target(target)
        send = self.sendGCode if report_error else lambda script: self.sendGCode(script, report_error=False)
        return send('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={:g}'.format(value))

    def preHeat(self, bedtemp, exttemp, toolnum=None, fan_speed=None):
        # Validate the whole preset before sending any command.
        commands = []
        if self.capabilities.bed:
            value = self.capabilities.bed.validate_target(bedtemp)
            commands.append('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={:g}'.format(value))
        heater = self.capabilities.active_hotend
        if toolnum is not None:
            name = 'extruder' + (str(toolnum) if toolnum else '')
            heater = next((item for item in self.capabilities.hotends if item.name == name), None)
            if heater is None:
                raise ValueError('Hotend is unavailable')
        if heater:
            value = heater.validate_target(exttemp)
            commands.append('SET_HEATER_TEMPERATURE HEATER={} TARGET={:g}'.format(heater.name, value))
        if fan_speed is not None and self.capabilities.fan:
            commands.append(self._fan_command(fan_speed))
        if commands:
            return self.sendGCode('\n'.join(commands))

    def setZOffset(self, offset, report_error=True):
        offset = float(offset)
        if not math.isfinite(offset) or not self.Z_PROBE_OFFSET_RANGE_MIN <= offset <= self.Z_PROBE_OFFSET_RANGE_MAX:
            raise ValueError('Runtime Z offset is outside the supported range')
        send = self.sendGCode if report_error else lambda script: self.sendGCode(script, report_error=False)
        return send('SET_GCODE_OFFSET Z=%s MOVE=1' % offset)


