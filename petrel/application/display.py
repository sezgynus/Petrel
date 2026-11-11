"""Compose feature views and own the display application lifecycle."""
from petrel.features.buzzer.control import Settings as BuzzerSettings
from petrel.application.startup import PanelStartupMixin
from petrel.application.tick import DisplayTickMixin
from petrel.application.input import DisplayInputMixin
from petrel.ui.selection import select_t
from petrel.ui.list_menu import ListMenuMixin
from petrel.ui.dashboard import DashboardMixin
from petrel.ui.header import HeaderMixin
from petrel.features.info.view import InfoViewMixin
from petrel.features.display_settings.view import DisplaySettingsViewMixin
from petrel.features.files.browser_view import FileBrowserMixin
from petrel.features.motion.view import MotionViewMixin
from petrel.features.temperature.view import TemperatureViewMixin
from petrel.features.leveling.probe_view import ProbeViewMixin
from petrel.ui.home import HomeViewMixin
from petrel.artwork.resources import ICON_FLOW, ICON_LIGHT, ICON_MOTION, ICON_MOTOR_OFF, ICON_PREHEAT_PROFILE
from petrel.artwork.resources import ICON_LIBRARY_ID
import petrel.features.display_settings.settings as display_settings
from petrel.features.nfc.share_view import NFCURIShareComponent
import time
import logging
from concurrent.futures import Future
from petrel.ui.command_feedback import CommandFeedback
from threading import Lock
from petrel.ui.events import UIEventLoop
from petrel.features.case_light.view import CaseLightMixin
from petrel.features.maintenance.ui.view import MaintenanceViewMixin
from petrel.features.recovery.view import RecoveryViewMixin
from petrel.features.power.view import PowerShortcutMixin
from petrel.features.mmu.view import MMUViewMixin
from petrel.features.buzzer.view import BuzzerViewMixin
from petrel.features.nfc.settings_view import NFCSettingsViewMixin
from petrel.features.nfc.view import RFIDViewMixin
from petrel.features.leveling.screws_tilt_view import ScrewsTiltMixin
from petrel.features.leveling.bed_mesh_view import BedMeshMixin
from petrel.features.files.preview import FilePreviewMixin
from petrel.features.printing.view import PrintFocusMixin
from petrel.features.power.lifecycle import PowerMonitor

from petrel.hardware.encoder import Encoder
from gpiozero import Button, Device
from gpiozero.pins.lgpio import LGPIOFactory
from petrel.printer.interface import PrinterData
from petrel.hardware.dwin.driver import T5UIC1Display, T5UIC1ProtocolError
from petrel.artwork.resources import ICON_DISPLAY_NORMAL, ICON_DISPLAY_SELECTED, ICON_MMU_HOME_NORMAL, ICON_MMU_HOME_SELECTED

def _MAX(lhs, rhs):
    if lhs > rhs:
        return lhs
    else:
        return rhs

class PetrelDisplay(
    PanelStartupMixin,
    DisplayTickMixin,
    DisplayInputMixin,
    ListMenuMixin,
    DashboardMixin,
    HeaderMixin,
    InfoViewMixin,
    DisplaySettingsViewMixin,
    FileBrowserMixin,
    MotionViewMixin,
    TemperatureViewMixin,
    ProbeViewMixin,
    HomeViewMixin,
    RFIDViewMixin,
    RecoveryViewMixin,
    PrintFocusMixin,
    PowerShortcutMixin,
    BuzzerViewMixin,
    NFCSettingsViewMixin,
    MMUViewMixin,
    CaseLightMixin,
    MaintenanceViewMixin,
    ScrewsTiltMixin,
    BedMeshMixin,
    FilePreviewMixin,
):

    TROWS = 6
    MROWS = TROWS - 1  # Total rows, and other-than-Back
    TITLE_HEIGHT = 30  # Title bar height
    MLINE = 53         # Menu line height
    LBLX = 60          # Menu item label X
    MENU_CHR_W = 8
    # Shared right edge for menu values (exclusive). Different numeric field
    # widths keep their own left edge without changing this alignment.
    MENU_VALUE_RIGHT = 240
    MENU_NARROW_CELLS = 3
    MENU_WIDE_CELLS = 7
    MENU_MOTION_CELLS = 9
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
    RFIDMenu = 51
    NFCSettingsMenu = 52
    NFCChoiceMenu = 53
    NFCGateMenu = 54
    EventSoundsMenu = 55

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
    ICON_More = 16

    ICON_Axis = 17
    ICON_CloseMotor = ICON_MOTOR_OFF
    ICON_Homing = 18
    ICON_SetHome = 19
    ICON_PLAPreheat = ICON_PREHEAT_PROFILE
    ICON_Cool = 20

    ICON_MoveX = 21
    ICON_MoveY = 22
    ICON_MoveZ = 23
    ICON_Extruder = 24

    ICON_Temperature = 26
    ICON_Motion = ICON_MOTION
    ICON_WriteEEPROM = 27
    ICON_ReadEEPROM = 28
    ICON_Info = 29
    ICON_CaseLight = ICON_LIGHT

    ICON_FanSpeed = 30

    ICON_StockConfiguraton = 28
    ICON_MaxSpeedX = ICON_MoveX
    ICON_MaxSpeedY = ICON_MoveY
    ICON_MaxSpeedZ = ICON_MoveZ
    ICON_StepE = ICON_FLOW
    ICON_BLTouch = 31
    ICON_TempTooLow = 32
    ICON_NoTips_C = 33
    ICON_NoTips_E = 34
    ICON_Continue_C = 35
    ICON_Cancel_C = 36
    ICON_Confirm_C = 37
    ICON_Maintenance_0 = 38
    ICON_Maintenance_1 = 39
    ICON_Info_0 = 40
    ICON_Info_1 = 41

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
        self._nfc_share_popup = None
        self._power_focus = False
        self._power_origin = None
        self._power_confirm_yes = True
        self._loop = UIEventLoop(self._initialize, self._process_input,
                                 self._ui_tick, self._close_resources, interval=.5)
        self._loop.start()

    def _initialize(self):
        enabled, socket_path, output, font = self._emulator_options
        if enabled:
            from petrel.emulator.runtime import Emulator, ScreenshotServer
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
        self._event_buzzer_ready = False
        self._sound_event_prefs_ready = False
        self._buzzer_load_complete = False
        self.pd.subscription.set_melody_callback(self._queue_buzzer_melody)
        self.pd.init_Webservices()
        # NFC stays alive on every menu and during every printer state.
        core = self.pd.get_nfc_core()
        if core is not None:
            self._nfc_emergency_sound_token = self._subscribe_emergency_buzzer(core)
            self._nfc_ui_token = self._subscribe_nfc_card_notifications(core)
            self._nfc_status_token = core.subscribe('reader.changed',
                lambda state: self._queue_nfc_ui_event('nfc_status'))
            self._nfc_capability_token = core.subscribe('capabilities.changed',
                lambda state: self._queue_nfc_ui_event('nfc_capabilities'))
            self._nfc_share_done_token = core.subscribe('share.ndef_transferred',
                lambda state: self._queue_nfc_ui_event('nfc_share_done'))
            self._nfc_share_failed_token = core.subscribe('share.failed',
                lambda state: self._queue_nfc_ui_event('nfc_share_failed'))
            self._nfc_share_cancel_token = core.subscribe('share.cancelled',
                lambda state: self._queue_nfc_ui_event('nfc_share_cancelled'))
        self.pd.sync_nfc_event()
        self._nfc_uri_share = NFCURIShareComponent(core)
        if core is not None:
            from petrel.features.nfc.spool_router import NFCSpoolRouter
            self._nfc_spool_router = NFCSpoolRouter(
                core, self.pd.nfc_lookup_spool,
                lambda: self._queue_nfc_ui_event('nfc_gate_lookup'))
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
                from petrel.emulator.remote import RemoteDisplayServer
                self._remote_display = RemoteDisplayServer(
                    self._emulator, self._remote_input,
                    port=self._remote_options[1], host=self._remote_options[2],
                    report_provider=self.pd.maintenance_book.exported,
                    trace_provider=self.pd.export_maintenance_test_recording)
            except (OSError, RuntimeError, ValueError):
                # The normal physical LCD must remain functional even if
                # The chosen interface is unavailable or port 8088 is occupied.
                logging.exception('Remote Display unavailable; continuing with physical LCD')

    def _action(self, label, callback, expected=None, confirmation_timeout=300.0,
                on_accept=None, silent=False):
        if getattr(self, '_action_feedback', None) is not None:
            return None
        try:
            future = callback()
        except ValueError as error:
            logging.warning('LCD action %s rejected: %s', label, error)
            future = Future()
            future.set_exception(error)
        if isinstance(future, Future):
            self._action_feedback = CommandFeedback(
                future, label, self.pd.state.epoch, expected, confirmation_timeout)
            self._action_on_accept = on_accept
            self._action_silent = silent
        return future

    def _restore_action_screen(self):
        screens = {self.Prepare: self.Draw_Prepare_Menu, self.Control: self.Draw_Control_Menu,
                   self.TemperatureID: self.Draw_Temperature_Menu, self.Tune: self.Draw_Tune_Menu,
                   self.Motion: self.Draw_Motion_Menu, self.AxisMove: self.Draw_Move_Menu,
                   self.CaseLight: self.Draw_Case_Light_Menu}
        if self.checkkey == self.Last_Prepare and self.pd.ishomed():
            self.CompletedHoming()
        elif self.checkkey in screens:
            screens[self.checkkey]()
        else:
            self.HMI_StartFrame(False)
        self.lcd.update()

    def _poll_action(self):
        feedback = getattr(self, '_action_feedback', None)
        if feedback is None:
            return False
        silent = getattr(self, '_action_silent', False)
        phase = feedback.update(self.pd.state, bool(self.pd.connection_error))
        if phase == 'accepted':
            self._stop_waiting = False
            self._action_feedback = None
            on_accept = getattr(self, '_action_on_accept', None)
            self._action_on_accept = None
            if on_accept is not None:
                on_accept()
            if not silent:
                self.HMI_AudioFeedback(True)
                self._restore_action_screen()
            self._action_silent = False
            return False
        if phase == 'waiting' and silent:
            return False
        if phase == 'error':
            self._stop_waiting = False
            self._action_on_accept = None
            self.pd.last_command_error = None
        self._show_message(feedback.message)
        return True

    def _configure_menus(self):
        caps = self.pd.capabilities
        recovery = self.pd.jog_recovery_required
        preset_revision = getattr(self.pd, 'preset_revision', 0)
        if getattr(self, '_menu_preset_revision', preset_revision) != preset_revision and getattr(self, 'checkkey', self.MainMenu) in (self.PLAPreheat, self.ABSPreheat):
            self.checkkey = self.TemperatureID
            self.select_temp.reset()
            self._active_preset = 0
        if (getattr(self, '_menu_capabilities', None) == caps
                and getattr(self, '_menu_recovery', False) == recovery
                and getattr(self, '_menu_preset_revision', -1) == preset_revision):
            return False
        self._menu_capabilities = caps
        self._menu_recovery = recovery
        self._menu_preset_revision = preset_revision
        heat = self.pd.HAS_HOTEND or self.pd.HAS_HEATED_BED
        self._menus = {
            'prepare': [('MOVE', 'Move', self.ICON_Axis), ('DISA', 'Disable steppers', self.ICON_CloseMotor),
                        ('HOME', 'Home', self.ICON_Homing), ('ZOFF', 'Runtime Z offset', self.ICON_Zoffset)],
            'tune': [('SPEED', 'Print speed', self.ICON_Speed)],
            'temperature': [], 'preheat': [], 'control': [],
        }
        for menu in ('tune', 'temperature', 'preheat'):
            if self.pd.HAS_HOTEND:
                self._menus[menu].append(('TEMP', 'Hotend temp', self.ICON_HotendTemp))
            if self.pd.HAS_HEATED_BED:
                self._menus[menu].append(('BED', 'Bed temp', self.ICON_BedTemp))
            if self.pd.HAS_FAN and menu != 'preheat':
                self._menus[menu].append(('FAN', 'Fan speed', self.ICON_FanSpeed))
        self._menus['tune'].append(('ZOFF', 'Runtime Z offset', self.ICON_Zoffset))
        if heat:
            for index, preset in enumerate(self.pd.material_preset):
                key = 'PRESET:' + str(index)
                self._menus['prepare'].append((key, 'Preheat ' + preset.name, self.ICON_PLAPreheat))
            self._menus['prepare'].append(('COOL', 'Cooldown', self.ICON_Cool))
        if self.pd.HAS_HOTEND:
            for index, preset in enumerate(self.pd.material_preset):
                key = 'PRESET:' + str(index)
                self._menus['temperature'].append((key, preset.name + ' settings', self.ICON_PLAPreheat))
        self._menus['preheat'].append(('SAVE', 'Save settings', self.ICON_WriteEEPROM))
        self._menus['preheat'].append(('CANCEL', 'Discard changes', self.ICON_Back))
        if heat or self.pd.HAS_FAN:
            self._menus['control'].append(('TEMP', 'Temperature', self.ICON_Temperature))
        self._menus['control'].append(('MOVE', 'Motion', self.ICON_Motion))
        if recovery:
            self._menus['control'].append(('RECOVERY', 'Restore jog state', self.ICON_Homing))
        if caps.case_light:
            self._menus['control'].append(('LIGHT', 'Case Light', self.ICON_CaseLight))
        self._menus['control'].append(('INFO', 'Info', self.ICON_Info))
        prefixes = {'prepare': 'PREPARE', 'temperature': 'TEMP', 'tune': 'TUNE',
                    'preheat': 'PREHEAT', 'control': 'CONTROL'}
        keys = ('MOVE', 'DISA', 'HOME', 'ZOFF', 'COOL', 'SPEED', 'TEMP', 'BED', 'FAN',
                'SAVE', 'INFO', 'PROBE', 'RECOVERY', 'LIGHT', 'SCREWS', 'MESH')
        for menu, prefix in prefixes.items():
            for key in keys:
                setattr(self, prefix + '_CASE_' + key, -1)
            for index, (key, _, _) in enumerate(self._menus[menu], 1):
                setattr(self, prefix + '_CASE_' + key, index)
            setattr(self, prefix + '_CASE_TOTAL', len(self._menus[menu]))
        return True

    def lcdExit(self):
        self._loop.close()

    def wait(self):
        self._loop.wait()

    def _close_resources(self):
        if self._closed:
            return
        self._spool_stop_scan_animation()
        self._event_buzzer_ready = False
        self.pd.subscription.set_melody_callback(None)
        self._closed = True
        for resource in (getattr(self, '_software_update', None),
                         getattr(self, '_remote_display', None),
                         getattr(self, '_nfc_spool_router', None),
                         getattr(self, '_buzzer_player', None),
                         getattr(self, '_screenshot_server', None),
                         getattr(self, '_emulator', None),
                         getattr(self, '_power_monitor', None), self.button, self.encoder, self.pd):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    logging.exception('LCD resource cleanup failed')
        if self.lcd is not None:
            self.lcd.close()
        probe = getattr(self, '_panel_probe', None)
        if probe is not None:
            probe.close()

    def _show_message(self, message):
        self.Clear_Main_Window()
        self.lcd.draw_text(False, True, self.lcd.DWIN_FONT_STAT,
                             self.lcd.Color_White, self.lcd.Color_Bg_Black,
                             10, 50, message)
        self.lcd.update()

    def HMI_StartFrame(self, with_update):
        self._present_print_state()
        if not self._print_error_visible:
            self.Draw_Status_Area(with_update)

    def _maintenance_panel_api(self,action,*args):
        lcd = self.lcd
        if lcd is None or not self._uart_online:
            raise ValueError('lcd_offline')
        if action=='info':
            info = {'uart_epoch':self._uart_epoch,
                    'startup_assets_synced':bool(getattr(lcd,'_assets_synced',False)),
                    'gpio_button_presses':getattr(self,'_maintenance_button_presses',0)}
            provider = getattr(lcd,'diagnostics',None)
            if callable(provider):
                info.update(provider())
            provider = getattr(self.encoder,'diagnostics',None)
            if callable(provider):
                info.update(provider())
            return info
        if action=='capture':
            raw = getattr(lcd,'_backlight_raw',None)
            if type(raw) is not int:
                raise ValueError('runtime_brightness_unknown')
            return raw
        if action in ('brightness','restore'):
            value,epoch = args
            if epoch!=self._uart_epoch:
                raise ValueError('lcd_session_changed')
            lcd.set_backlight(display_settings.raw_brightness(value) if action=='brightness' else value)
            return True
        raise ValueError('panel_action_unavailable')

    def HMI_AudioFeedback(self, success=True):
        if (success):
            self.pd.buzzer.tone(100, 659)
            self.pd.buzzer.tone(10, 0)
            self.pd.buzzer.tone(100, 698)
        else:
            self.pd.buzzer.tone(40, 440)

