from klipper_recovery import KlipperRecovery
from print_estimates import progress as print_progress, estimates as print_estimates, number as time_number
import copy
from dataclasses import replace
import logging
import math
import re
import sys
import time
import uuid
from urllib.parse import quote
from collections.abc import Mapping
from concurrent.futures import Future, CancelledError
from threading import Lock
from display_numbers import js_round
from background_reads import ReadWorker, ReadPending
from operation_guards import motion_dispatch_guard
from motion_settings import PARAMETERS, validate as validate_motion
from moonraker_client import MoonrakerClient, MoonrakerError
from moonraker_subscription import MoonrakerSubscription
from probe_wizard import ProbeWizard
from screws_tilt import ScrewsTiltSession
from bed_mesh import BedMeshSession
from mmu_control import MMUSession
from preset_store import PresetStore
from printer_state import PrinterState
from printer_capabilities import PrinterCapabilities
from maintenance_session import MaintenanceDiscoveryManager
from maintenance_controller import MaintenanceReadController
from maintenance_guided import guided_plan
from maintenance_switches import MaintenanceSwitchController
from maintenance_motion_controller import MaintenanceMotionController
from maintenance_probe import MaintenanceProbeController
from maintenance_resonance import MaintenanceResonanceController
from maintenance_filament import MaintenanceFilamentController
from maintenance_panel import MaintenancePanelController
from maintenance_auxiliary import MaintenanceAuxiliaryController
from maintenance_records import MaintenanceBook
from maintenance_assessment_service import MaintenanceAssessment
from maintenance_system import travel_profile
from maintenance_physical import MaintenancePulseController
from maintenance_heater import MaintenanceHeaterController, MaintenancePhysicalRouter, thermal_plan
from rfid_reader import RFIDReader
from system_info import host_memory_usage, host_metrics, network_info, updater_version, wifi_info

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


class PrinterData:
    Z_PROBE_OFFSET_RANGE_MIN = -20
    Z_PROBE_OFFSET_RANGE_MAX = 20

    buzzer = buzz_t()

    BABY_Z_VAR = 0
    feedrate_percentage = 100
    flow_percentage = 100
    live_velocity = 0.0
    live_extruder_velocity = 0.0
    volumetric_flow = 0.0
    live_position = (0.0, 0.0, 0.0)
    dashboard_fan_pwm = 0
    temphot = 0
    tempbed = 0

    HMI_ValueStruct = HMI_value_t()
    HMI_flag = HMI_Flag_t()

    current_position = xyze_t()

    thermalManager = {
        'temp_bed': {'celsius': 0, 'target': 0},
        'temp_hotend': [{'celsius': 0, 'target': 0}],
        'fan_speed': [0]
    }

    material_preset = [
        material_preset_t('PLA', 200, 60),
        material_preset_t('ABS', 210, 100)
    ]
    files = None
    MACHINE_SIZE = 'unknown'
    SHORT_BUILD_VERSION = "unknown"
    CORP_WEBSITE_E = "github.com/sezgynus/Petrel"

    def __init__(self, API_Key='', URL='http://127.0.0.1:7125', timeout=5.0, settings_path=None,
                 power_device='Printer'):
        self.client = MoonrakerClient(URL, API_Key, timeout)
        self._read_worker = ReadWorker(timeout)
        # HTTP maintenance can wait up to 120s; never hold normal telemetry,
        # file browsing or preset reads behind an update request.
        self._maintenance_worker = ReadWorker(timeout=1, capacity=2, queue_timeout=120)
        self._read_jobs = {}
        self._settings_save = None
        self._files_loading = self._directory_loading = False
        self._file_retry_at = 0.0
        self._directory_retry_at = {}
        self._directory_revision_key = None
        self.power_device = str(power_device).strip() or 'Printer'
        # Keep read-only Spoolman telemetry off the serialized printer-command
        # transport. A telemetry timeout must never cancel or delay user commands.
        self.spoolman_client = MoonrakerClient(URL, API_Key, timeout, queue_size=16)
        self._jog_lock = Lock()
        self._jog_restore = None
        self._jog_state_name = '_PETREL_JOG_' + uuid.uuid4().hex
        self.state = PrinterState()
        self.maintenance_book = MaintenanceBook(self._maintenance_worker)
        self.maintenance_assessment = MaintenanceAssessment()
        self._maintenance_panel_api = None
        self.maintenance = MaintenanceDiscoveryManager()
        self.capabilities = PrinterCapabilities()
        self._apply_capabilities(self.capabilities)
        self.status = None
        self.connection_error = None
        self.last_command_error = None
        self.absolute_moves = True
        self.absolute_extrude = True
        self.flow_percentage = 100
        self.live_velocity = 0.0
        self.live_extruder_velocity = 0.0
        self.volumetric_flow = 0.0
        self.live_position = (0.0, 0.0, 0.0)
        self.dashboard_fan_pwm = 0
        self.mmu = None
        self.mmu_session = MMUSession(self)
        self._spoolman_percentages = {}
        self._spoolman_futures = {}
        self._spoolman_refresh_at = {}
        self.file_name = ''
        self.job_Info = {'virtual_sdcard': {'is_active': False, 'progress': 0},
                         'print_stats': {'state': 'standby', 'print_duration': 0,
                                         'filename': ''}}
        self.current_position = xyze_t()
        self.HMI_ValueStruct = HMI_value_t()
        self.HMI_flag = HMI_Flag_t()
        self.thermalManager = copy.deepcopy(type(self).thermalManager)
        self.material_preset = []
        self.preset_store = PresetStore(settings_path)
        self.settings_error = None
        self.mainsail_presets_error = None
        self.presets_from_mainsail = False
        self.preset_revision = 0
        self.system_info = {
            'petrel': 'Unavailable',
            'moonraker': 'Unavailable',
            'mainsail': 'Unavailable',
            'network': 'Unknown',
            'wifi_ssid': 'Unavailable',
            'wifi_rssi': None,
            'ip': 'Unavailable',
            'host_cpu': None,
            'host_ram': None,
            'host_temp': None,
            'mcus': (),
        }
        self._system_info_refresh_at = 0.0
        self._system_info_refresh_interval = 5.0
        self._wifi_status_refresh_at = 0.0
        self._preset_refresh_at = 0.0
        self._preset_refresh_interval = 5.0
        self.refresh_mainsail_presets(force=True)
        try:
            saved = self.preset_store.load()
            if saved is not None and not self.presets_from_mainsail and not self.material_preset:
                self.material_preset = [material_preset_t(**item) for item in saved]
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            self.settings_error = str(error)
            logging.warning('Cannot load presets from %s: %s', self.preset_store.path, error)
        if not self.material_preset and not self.presets_from_mainsail:
            self.material_preset = copy.deepcopy(type(self).material_preset)
        self.files = []
        self._files_generation = 0
        self._root_prefetch_unretained = None
        self._files_paths_snapshot = ()
        self._file_thumbnail_keys = {}
        self._file_thumbnail_list = None
        self._file_sort_pending = None
        self.file_error = None
        self._files_loaded = False
        self._file_epoch = -1
        self._file_revision = -1
        self.file_sort = ('modified', True)
        self.file_sort_revision = 0
        self._file_sort_refresh_at = 0.0
        self._directory_cache = {}
        self._preset_original = copy.deepcopy(self.material_preset)
        self.subscription = MoonrakerSubscription(URL, API_Key, timeout)
        self.recovery = KlipperRecovery(self.client, self._read_worker,
            lambda: bool(self.connection_error) or not self.state.ready)
        self.probe_wizard = ProbeWizard(self)
        self.screws_tilt = ScrewsTiltSession(self)
        self.bed_mesh = BedMeshSession(self)
        # Created without I/O; reads happen only after an explicit request.
        self.maintenance_reader = MaintenanceReadController(
            self, self._maintenance_worker, self.client)
        self.maintenance_panel = MaintenancePanelController(self,self._maintenance_worker,self.client)
        self.maintenance_pulse = MaintenancePhysicalRouter(
            MaintenancePulseController(self, self._maintenance_worker, self.client),
            MaintenanceHeaterController(self, self._maintenance_worker, self.client),
            motion=MaintenanceMotionController(self, self._maintenance_worker, self.client),
            switches=MaintenanceSwitchController(self, self._maintenance_worker, self.client),
            probe=MaintenanceProbeController(self, self._maintenance_worker, self.client),
            resonance=MaintenanceResonanceController(self, self._maintenance_worker, self.client),
            filament=MaintenanceFilamentController(self, self._maintenance_worker, self.client),
            panel=self.maintenance_panel,
            auxiliary=MaintenanceAuxiliaryController(self,self._maintenance_worker,self.client))

    def _read(self, key, work, stamp=None):
        if stamp is None:
            reader = getattr(self.subscription, 'lifecycle', None) if hasattr(self, 'subscription') else None
            life = reader() if callable(reader) else None
            stamp = (life.get('epoch', 0) if isinstance(life, dict) else
                     self.subscription.snapshot().get('epoch', 0) if hasattr(self, 'subscription') else 0)
        job = self._read_jobs.get(key)
        if job is not None and job[0] != stamp:
            job[1].cancel()
            self._read_jobs.pop(key)
            job = None
        if job is None:
            if len(self._read_jobs) >= 32:
                oldest = next(iter(self._read_jobs))
                self._read_jobs.pop(oldest)[1].cancel()
            job = (stamp, self._read_worker.submit(work))
            self._read_jobs[key] = job
        if not job[1].done():
            raise ReadPending()
        self._read_jobs.pop(key)
        return job[1].result()

    def discover_serial_ports(self):
        """Fetch Moonraker's canonical UART list once, off the LCD UI thread."""
        from nfc_settings import serial_ports_from_moonraker
        return self._read_worker.submit(lambda: serial_ports_from_moonraker(
            self.client.get('/machine/peripherals/serial')))

    def refresh_nfc_info(self):
        """Read one shared background owner's snapshots, never touch UART here."""
        reader = getattr(self, '_rfid_reader', None)
        if reader is None:
            reader = self._rfid_reader = RFIDReader()
        revision, status, card = reader.snapshot()
        identity = reader.identity()
        token = (revision, status, card, identity)
        if token == getattr(self, '_rfid_token', None):
            return False
        self._rfid_token = token
        self.system_info['nfc'] = identity
        self.system_info['rfid'] = {'status': status, 'card': card}
        return True

    def refresh_rfid(self):
        return self.refresh_nfc_info()

    def refresh_wifi_status(self):
        """Keep header RSSI fresh on the existing read worker, without blocking UI."""
        now = time.monotonic()
        if now < self._wifi_status_refresh_at:
            return False
        try:
            ssid, rssi = self._read('wifi_status', wifi_info)
        except ReadPending:
            return False
        except (MoonrakerError, CancelledError, OSError, ValueError, TypeError, UnicodeError) as error:
            logging.debug('Wi-Fi status read unavailable: %s', error)
            ssid, rssi = 'Unavailable', None
        self._wifi_status_refresh_at = now + 5.0
        previous = (self.system_info.get('wifi_ssid'), self.system_info.get('wifi_rssi'))
        self.system_info['wifi_ssid'], self.system_info['wifi_rssi'] = ssid, rssi
        return previous != (ssid, rssi)

    def refresh_system_info(self, force=False):
        """Refresh component versions and host IPv4 without mutating printer state."""
        now = time.monotonic()
        if not force and now < self._system_info_refresh_at:
            return False

        previous = dict(self.system_info)
        current = dict(previous)
        try:
            # lifecycle() reads only connection metadata; snapshot() deep-copies
            # all subscribed objects and is unnecessary on every pending poll.
            lifecycle = self.subscription.lifecycle()
            epoch = (lifecycle.get('epoch', 0) if isinstance(lifecycle, Mapping)
                     else self.subscription.snapshot().get('epoch', 0))
            # Header and Info share one throttled Wi-Fi reader and its cache.
            response = self._read('system_info',
                lambda: self.client.get('/machine/update/status'),stamp=epoch)
            versions = response.get('result', {}).get('version_info', {})
            if not isinstance(versions, Mapping):
                raise ValueError('Invalid update-manager status')
            current['petrel'] = updater_version(versions, 'Petrel', full=True)
            current['moonraker'] = updater_version(versions, 'moonraker', full=True)
            current['mainsail'] = updater_version(versions, 'mainsail')
        except ReadPending:
            return False
        except (MoonrakerError, KeyError, TypeError, ValueError) as error:
            logging.debug('Cannot refresh component versions: %s', error)
        status, address = network_info()
        current['network'] = status
        current['ip'] = address
        cpu, temperature = host_metrics()
        current['host_ram'] = host_memory_usage()
        current['host_cpu'] = cpu
        current['host_temp'] = temperature
        mcus = []
        if self.state.ready:
            temperatures = []
            for object_name, value in self.state.status.items():
                if (not (object_name.startswith('temperature_sensor ') or
                         object_name.startswith('temperature_fan ')) or
                        not isinstance(value, Mapping)):
                    continue
                setting = next((item for key, item in self.state.settings.items()
                                if key.lower() == object_name.lower()), {})
                if not isinstance(setting, Mapping) or setting.get('sensor_type') != 'temperature_mcu':
                    continue
                # Klipper defaults temperature_mcu sensors to the primary MCU.
                sensor_mcu = setting.get('sensor_mcu', 'mcu')
                if not isinstance(sensor_mcu, str):
                    continue
                try:
                    temperature = float(value.get('temperature'))
                    if math.isfinite(temperature):
                        temperatures.append((sensor_mcu, temperature))
                except (TypeError, ValueError):
                    pass
            for object_name, value in self.state.status.items():
                if object_name != 'mcu' and not object_name.startswith('mcu '):
                    continue
                if not isinstance(value, Mapping):
                    continue
                stats = value.get('last_stats', {})
                load = None
                if isinstance(stats, Mapping):
                    try:
                        task_avg = float(stats.get('mcu_task_avg'))
                        task_stddev = float(stats.get('mcu_task_stddev'))
                        if math.isfinite(task_avg) and math.isfinite(task_stddev):
                            # Match Mainsail's MCU load calculation exactly.
                            ratio = task_avg + (3.0 * task_stddev) / 0.0025
                            load = max(0.0, min(100.0, ratio * 100.0))
                    except (TypeError, ValueError):
                        pass
                temperature = None
                for sensor_mcu, sensor_temperature in temperatures:
                    mcu_name = object_name if object_name == 'mcu' else object_name.split(' ', 1)[1]
                    if mcu_name == sensor_mcu:
                        temperature = sensor_temperature
                        break
                mcus.append({'name': object_name, 'load': load,
                             'temperature': temperature,
                             'version': str(value.get('mcu_version') or '')})
            current['mcus'] = tuple(mcus)
        self._system_info_refresh_at = now + self._system_info_refresh_interval
        self.system_info = current
        return current != previous

    @staticmethod
    def _preset_signature(presets):
        return tuple((item.mainsail_id, item.name, item.hotend_temp, item.bed_temp)
                     for item in presets)

    def refresh_mainsail_presets(self, force=False):
        now = time.monotonic()
        baseline = getattr(self, '_preset_baseline', None)
        if baseline is not None and baseline != self._preset_signature(self.material_preset):
            return False  # Keep the local draft until its explicit Save succeeds.
        if self._settings_save is not None:
            return False
        if not force and now < self._preset_refresh_at:
            return False
        try:
            mainsail = self._read('presets', lambda: self.client.get('/server/database/item?namespace=mainsail&key=presets.presets'))
            self._preset_refresh_at = now + self._preset_refresh_interval
            values = mainsail.get('result', {}).get('value', {})
            if not isinstance(values, Mapping):
                raise ValueError('Invalid Mainsail preset database')
            presets = []
            for preset_id, item in values.items():
                try:
                    presets.append(material_preset_t.from_mainsail(item, preset_id))
                except (ValueError, TypeError) as error:
                    logging.warning('Ignoring invalid Mainsail preset %s: %s', preset_id, error)
            self._preset_original = copy.deepcopy(presets)
            self._preset_baseline = self._preset_signature(presets)
            if not presets:
                changed = bool(self.material_preset)
                if changed:
                    self.material_preset = []
                    self.preset_revision += 1
                self.presets_from_mainsail = True
                self.mainsail_presets_error = None
                return changed
            changed = self._preset_signature(presets) != self._preset_signature(self.material_preset)
            if changed:
                self.material_preset = presets
                self.preset_revision += 1
            self.presets_from_mainsail = True
            self.mainsail_presets_error = None
            return changed
        except ReadPending:
            return False
        except (MoonrakerError, KeyError, ValueError, TypeError) as error:
            self._preset_refresh_at = now + self._preset_refresh_interval
            self.mainsail_presets_error = str(error)
            logging.warning('Cannot refresh Mainsail presets: %s', error)
            return False

    def _apply_capabilities(self, caps):
        self.HAS_HOTEND = caps.active_hotend is not None
        self.HOTENDS = len(caps.hotends)
        self.HAS_HEATED_BED = caps.bed is not None
        self.HAS_FAN = caps.fan
        self.HAS_BED_PROBE = caps.probe
        self.HAS_PREHEAT = caps.has_heaters
        self.HAS_ZOFFSET_ITEM = True
        self.HAS_ONESTEP_LEVELING = caps.bed_mesh
        self.PREVENT_COLD_EXTRUSION = True
        hotend = caps.active_hotend
        self.EXTRUDE_MINTEMP = hotend.min_extrude_temp if hotend else 0
        self.EXTRUDE_MAXLENGTH = hotend.max_extrude_distance if hotend else 0
        self.MAX_E_TEMP = hotend.maximum if hotend else 0
        self.MIN_E_TEMP = 0
        self.BED_MAX_TARGET = caps.bed.maximum if caps.bed else 0
        self.MIN_BED_TEMP = 0
        self.X_MIN_POS, self.Y_MIN_POS, self.Z_MIN_POS = caps.axis_minimum
        self.X_MAX_POS, self.Y_MAX_POS, self.Z_MAX_POS = caps.axis_maximum
        self.MACHINE_SIZE = 'x'.join('{:g}'.format(value) for value in caps.build_size)

    def close(self):
        reader = getattr(self, '_rfid_reader', None)
        if reader is not None:
            reader.close()
        self.recovery.close()
        self.maintenance_pulse.close()
        self.maintenance_reader.close()
        barrier = getattr(self.subscription, 'wait_for_emergency_requests', None)
        if callable(barrier) and not barrier(timeout=3.0):
            logging.error('Maintenance safety stop unconfirmed during shutdown')
        self.maintenance.clear()
        # TEMPORARY MAINTENANCE TEST TRACE: preserve shutdown tail.
        trace = getattr(self,'maintenance_test_trace',None)
        if trace is not None:
            trace.stop()
        self.subscription.close()
        self._read_worker.close()
        self._maintenance_worker.close()
        self.maintenance_book.close()
        self.spoolman_client.close()
        # Started HTTP reads cannot be forcibly cancelled. Release their shared
        # transport only after BOTH workers have relinquished ownership.
        workers = [w for w in (self._read_worker, self._maintenance_worker)
                   if callable(getattr(type(w), 'on_stopped', None))]
        remaining = len(workers)
        release_lock = Lock()
        def release():
            nonlocal remaining
            with release_lock:
                remaining -= 1
                if remaining == 0:
                    self.client.close()
        if not workers:
            self.client.close()
        for worker in workers:
            worker.on_stopped(release)
        if trace is not None:
            trace.flush()

    # BEGIN TEMPORARY MAINTENANCE TEST TRACE
    def toggle_maintenance_test_recording(self):
        if self.maintenance_pulse.pending or self.maintenance_reader.pending:
            return False
        trace = getattr(self,'maintenance_test_trace',None)
        if trace is not None and trace.active:
            trace.stop()
        else:
            if trace is None:
                from maintenance_test_trace import TestTrace
                trace = self.maintenance_test_trace = TestTrace(self)
            trace.start()
            trace.tick(self.state)
        return True

    def maintenance_test_recording_label(self):
        trace = getattr(self,'maintenance_test_trace',None)
        return trace.label if trace is not None else 'Start test recording'

    def export_maintenance_test_recording(self):
        trace = getattr(self,'maintenance_test_trace',None)
        return trace.exported() if trace is not None else None
    # END TEMPORARY MAINTENANCE TEST TRACE

    def _note_maintenance_state(self,state):
        book = getattr(self,'maintenance_book',None)
        if book is not None:
            book.note(state,snapshot=getattr(getattr(self,'maintenance',None),'snapshot',None))
        # TEMPORARY MAINTENANCE TEST TRACE
        trace = getattr(self,'maintenance_test_trace',None)
        if trace is not None:
            trace.tick(state)

    def maintenance_integrations(self,state):
        services = ['maintenance.records','maintenance.usage_counters','maintenance.report_export']
        if travel_profile(state):
            services.append('maintenance.travel_counter')
        if callable(getattr(self,'_maintenance_panel_api',None)):
            services.extend(('petrel.uart_diagnostics','petrel.encoder_diagnostics',
                             'petrel.lcd_diagnostics','petrel.backlight'))
        return tuple(services)

    def maintenance_local_read(self,feature):
        if feature in ('S11','S12','S20'):
            return self.maintenance_book.read(feature)
        if feature in ('S14','S15','S16') and callable(getattr(self,'_maintenance_panel_api',None)):
            data = self._maintenance_panel_api('info')
            prefix = 'gpio_' if feature=='S15' else None
            keys = ('startup_assets_synced','uart_epoch') if feature=='S16' else (
                    tuple(k for k in data if k.startswith(prefix)) if prefix else
                    tuple(k for k in data if not k.startswith('gpio_')))
            return tuple((k,data[k]) for k in keys if type(data.get(k)) in (int,float,bool))
        return ()

    def _record_maintenance_result(self,result,method,plan=None):
        if result is not None:
            book = getattr(self,'maintenance_book',None)
            if book is not None:
                book.record(result,method,self.state,plan)
            assessment = getattr(self,'maintenance_assessment',None)
            if assessment is not None:
                try:
                    assessment.ingest(result,method,self.state)
                except (ValueError, TypeError, AttributeError):
                    logging.warning('Maintenance assessment evidence rejected')
        return result

    def maintenance_ui_records(self, operation, policy=None, history=False):
        from maintenance_ui_records import request
        rows=tuple(self.maintenance_guided_plan())+tuple(self.maintenance_read_plan())
        devices=self.maintenance_service_devices(rows)
        return request(self._maintenance_worker,operation,policy=policy,devices=devices,history=history,
            usage_provider=self.maintenance_book.service_counters,
            filament_provider=self.maintenance_filament_usage)

    def maintenance_filament_usage(self):
        from maintenance_filament_usage import recorded_filament
        return recorded_filament(self.client)

    def maintenance_sensor_devices(self):
        from maintenance_sensor_diagnostics import devices
        return devices(self.maintenance.snapshot)

    def maintenance_sensor_diagnostic(self,device):
        from maintenance_sensor_diagnostics import read
        if device not in self.maintenance_sensor_devices():
            raise ValueError('sensor_device_no_longer_available')
        state = self.state
        return self._maintenance_worker.submit(
            lambda: read(self.client, state, device), queue_timeout=8)

    def maintenance_service_bases(self,device):
        bases=('calendar_s','sampled_print_s')
        # History totals are printer-wide, not individual nozzle usage.
        extruders=tuple(x for x in self.state.objects if x=='extruder' or
                        x.startswith('extruder') and x[8:].isdigit())
        if device=='extruder' and extruders==('extruder',):
            bases += ('filament_mm',)
        from maintenance_travel import installed, AXES, travel_device
        if travel_device(device) in AXES and installed(self.state):
            return bases+('travel_mm',)
        from maintenance_sensor_usage import event_sample
        sample=event_sample(self.state)
        if sample is not None and device in sample[1] and device not in sample[3]:
            bases += ('trigger_count',)
        snapshot=self.maintenance.snapshot
        return bases+tuple(dict.fromkeys(m.metric_id for m in getattr(snapshot,'usage_metrics',())
                                          if m.device==device))

    def maintenance_service_devices(self,rows=()):
        snapshot=self.maintenance.snapshot
        from maintenance_travel import installed, AXES
        return tuple(dict.fromkeys(
            (AXES if installed(self.state) else ())+
            tuple(getattr(snapshot,'care_devices',()))+
            tuple(d.name for d in getattr(snapshot,'devices',()))+
            tuple(m.device for m in getattr(snapshot,'usage_metrics',()))+
            tuple(r.device for r in rows if r.device is not None)))

    def maintenance_reference(self,operation,result,*,relative_limit=None,confirmed=False):
        from maintenance_reference import request
        snapshot=self.maintenance.snapshot
        identity=(getattr(snapshot,'epoch',None),getattr(snapshot,'config_marker',None))
        operation_id=getattr(result,'operation_id','')
        if not self.maintenance_assessment.current_operation(snapshot,operation_id):
            raise ValueError('reference_measurement_stale')
        def current():
            live=self.maintenance.snapshot
            return (self.state.ready and live is not None and
                (live.epoch,live.config_marker)==identity)
        return request(self._maintenance_worker,operation,result,self.state,
            relative_limit=relative_limit,confirmed=confirmed,current=current)

    def accept_maintenance_reference(self,result):
        if not self.maintenance_assessment.current_operation(self.maintenance.snapshot,result.operation_id):
            return False
        if result.reset_device is not None:
            self.maintenance_assessment.invalidate_trends(result.reset_device)
        if result.finding is None: return True
        return self.maintenance_assessment.accept_trend(
            self.maintenance.snapshot,result.operation_id,result.finding)

    def _maintenance_assessment_rows(self):
        from maintenance_heater import thermal_plan
        rows=tuple(self.maintenance_read_plan())+tuple(self.maintenance_guided_plan())
        return tuple(dict.fromkeys(rows+thermal_plan(self.maintenance.snapshot)))

    def maintenance_assessment_details(self, **policies):
        rows = self._maintenance_assessment_rows()
        return self.maintenance_assessment.detailed_report(
            self.maintenance.snapshot, rows, **policies)

    def maintenance_assessment_report(self):
        rows = self._maintenance_assessment_rows()
        return self.maintenance_assessment.report(self.maintenance.snapshot, rows)

    def maintenance_read_plan(self):
        return self.maintenance_reader.available()

    def maintenance_guided_plan(self):
        # Passive target discovery only; not an actuation authorization.
        owner = getattr(self, 'maintenance_pulse', None)
        return owner.available() if owner is not None else guided_plan(self.maintenance.snapshot)

    def start_maintenance_physical(self, feature_id, device=None, **kwargs):
        return self.maintenance_pulse.start(feature_id, device, **kwargs)

    def poll_maintenance_physical(self):
        row = getattr(self.maintenance_pulse,'_row',None)
        return self._record_maintenance_result(self.maintenance_pulse.poll(),getattr(row,'method',None),row)

    def confirm_maintenance_physical(self):
        return self.maintenance_pulse.confirm()

    def observe_maintenance_physical(self, seen):
        row = getattr(self.maintenance_pulse,'_row',None)
        return self._record_maintenance_result(self.maintenance_pulse.observe(seen),getattr(row,'method',None),row)

    def confirm_maintenance_f12_stopped(self):
        row = getattr(self.maintenance_pulse,'_row',None)
        result,reason = self.maintenance_pulse.f12_confirm_stopped()
        if result is not None and type(result) is not bool:
            self._record_maintenance_result(result,getattr(row,'method',None),row)
        return result,reason

    def cancel_maintenance_physical(self):
        row = getattr(self.maintenance_pulse,'_row',None)
        return self._record_maintenance_result(self.maintenance_pulse.cancel(),getattr(row,'method',None),row)

    def start_maintenance_read(self, feature_id, timeout=8.0, device=None):
        return self.maintenance_reader.start(feature_id, timeout=timeout, device=device)

    def poll_maintenance_read(self):
        row = self.maintenance_reader._row
        return self._record_maintenance_result(self.maintenance_reader.poll(),16,row)

    def cancel_maintenance_read(self):
        row = self.maintenance_reader._row
        return self._record_maintenance_result(self.maintenance_reader.cancel(),16,row)

    def check_command_results(self):
        from queue import Empty
        while True:
            try:
                path, future = self.client.command_results.get_nowait()
            except Empty:
                return
            if future.cancelled():
                continue
            error = future.exception()
            if error:
                self.last_command_error = str(error)
                logging.error('LCD command %s failed: %s', path, error)

    # ------------- Klipper Function ----------

    def ishomed(self):
        if not self.connection_error and self.current_position.home_x and self.current_position.home_y and self.current_position.home_z:
            return True
        else:
            return False

    # ------------- Moonraker transport ----------

    def getREST(self, path):
        return self.client.get(path)

    def postREST(self, path, json, cleanup=None, report_error=True,
                 dispatch_guard=None, request_timeout=None):
        snapshot = self.subscription.snapshot()
        if (self.connection_error or not self.state.ready or snapshot['state'] != 'ready'
                or snapshot['epoch'] != self.state.epoch):
            from concurrent.futures import Future, CancelledError
            future = Future()
            future.cleanup_complete = cleanup is not None
            future.set_exception(MoonrakerError('Printer connection is not ready'))
            self.last_command_error = 'Printer connection is not ready'
            return future
        epoch = snapshot['epoch']

        def guard():
            current = self.subscription.snapshot()
            return current['state'] == 'ready' and current['epoch'] == epoch

        def operation_guard():
            return guard() and (dispatch_guard is None or dispatch_guard())

        # Only explicitly requesting callers override the normal transport
        # timeout. Keep the default path untouched for every existing
        # printer operation; the override remains bounded by MoonrakerClient.
        options = {'guard': operation_guard, 'report_error': report_error}
        if cleanup is not None:
            options.update(cleanup=cleanup, cleanup_guard=guard)
        if request_timeout is not None:
            options['request_timeout'] = request_timeout
        return self.client.post(path, json, **options)

    def power_on_if_off(self):
        """Turn on the configured Moonraker power device only when it is off."""
        payload = {'device': self.power_device, 'action': 'on'}

        def device_is_off():
            result = self.client.get('/machine/device_power/devices').get('result', {})
            devices = result.get('devices', []) if isinstance(result, dict) else []
            target = next((item for item in devices
                           if str(item.get('device', '')).casefold() == self.power_device.casefold()), None)
            if target is None:
                raise MoonrakerError('Configured power device was not found')
            if target.get('status') != 'off':
                raise MoonrakerError('Configured power device is not off')
            payload['device'] = target['device']
            return True

        # This intentionally bypasses postREST(): Moonraker must be able to
        # switch the PSU on while Klipper itself is offline.
        return self.client.post('/machine/device_power/device', payload,
                                guard=device_is_off, report_error=False)

    def power_off_block_reason(self):
        if self.maintenance_pulse.pending:
            return 'Maintenance operation is active'
        snapshot = self.subscription.snapshot()
        status = snapshot.get('status', {})
        if status.get('print_stats', {}).get('state') in ('printing', 'paused', 'pausing'):
            return 'Print is active'
        if (status.get('manual_probe', {}).get('is_active')
                or self.jog_recovery_required
                or any(getattr(getattr(self,name,None),'pending',None)
                       for name in ('bed_mesh','screws_tilt','probe_wizard','mmu_session'))):
            return 'Operation is running'
        mmu = status.get('mmu', {})
        if mmu and str(mmu.get('action', 'idle')).lower() not in ('idle','unknown'):
            return 'MMU is running'
        return None

    def power_off_if_on(self):
        """Turn off the configured Moonraker power device only when it is on."""
        payload = {'device': self.power_device, 'action': 'off'}

        def device_is_on():
            if hasattr(self, 'subscription') and self.power_off_block_reason():
                raise MoonrakerError('Power off is blocked by an active operation')
            result = self.client.get('/machine/device_power/devices').get('result', {})
            devices = result.get('devices', []) if isinstance(result, dict) else []
            target = next((item for item in devices
                           if str(item.get('device', '')).casefold() == self.power_device.casefold()), None)
            if target is None:
                raise MoonrakerError('Configured power device was not found')
            if target.get('status') != 'on':
                raise MoonrakerError('Configured power device is not on')
            if hasattr(self, 'subscription') and self.power_off_block_reason():
                raise MoonrakerError('Power off is blocked by an active operation')
            payload['device'] = target['device']
            return True

        return self.client.post('/machine/device_power/device', payload,
                                guard=device_is_on, report_error=False)

    def init_Webservices(self):
        # Bootstrap and reconnection run on the subscription thread.
        return self.update_variable()

    def _invalidate_files(self):
        """Release all owners of file data together across backend sessions."""
        self._files_generation += 1
        self.files = []
        self._files_paths_snapshot = ()
        self._file_thumbnail_keys = {}
        self._file_thumbnail_list = None
        self._files_loaded = self._files_loading = self._directory_loading = False
        self._file_retry_at = 0.
        self._directory_cache.clear()
        self._directory_retry_at.clear()
        self._directory_revision_key = None
        self._root_prefetch_unretained = None
        for name in ('_directory_cache_sizes', '_directory_orders'):
            getattr(self, name, {}).clear()
        pending, self._file_sort_pending = self._file_sort_pending, None
        if pending is not None:
            pending[2].cancel()
        for key in tuple(self._read_jobs):
            if key == 'files' or isinstance(key, tuple) and key[0] in ('directory', 'directory_sort'):
                self._read_jobs.pop(key)[1].cancel()

    def _file_sort_identity(self):
        return (self.state.epoch, self.state.file_revision, id(self.files), self.file_sort_revision)

    def _poll_file_sort(self, now):
        identity, preference, future = self._file_sort_pending
        if identity != self._file_sort_identity():
            future.cancel()
            self._file_sort_pending = None
            self._file_sort_refresh_at = 0.
            return False
        if not future.done():
            return False
        self._file_sort_pending = None
        self._file_sort_refresh_at = now + 5.
        try:
            files, paths = future.result()
        except Exception as error:
            logging.debug('File resort unavailable: %s', type(error).__name__)
            return False
        old_files = self.files
        self.files = files
        self._files_paths_snapshot = paths
        if self._file_thumbnail_list is old_files:
            self._file_thumbnail_list = files
        self.file_sort = preference
        self.file_sort_revision += 1
        return True

    def refresh_file_sort(self, force=False):
        now = time.monotonic()
        if self._file_sort_pending is not None:
            return self._poll_file_sort(now)
        if not force and now < self._file_sort_refresh_at:
            return False
        try:
            response = self._read('file_sort', lambda: self.client.get('/server/database/item?namespace=mainsail&key=view.gcodefiles'))
            self._file_sort_refresh_at = now + 5.0
            values = response.get('result', {}).get('value', {})
            if not isinstance(values, Mapping):
                raise ValueError('Invalid file sort settings')
            field = values.get('sortBy', 'modified')
            descending = values.get('sortDesc', True)
            if field not in ('filename', 'modified', 'size') or not isinstance(descending, bool):
                field, descending = 'modified', True
            preference = (field, descending)
        except ReadPending:
            return False
        except (MoonrakerError, KeyError, TypeError, ValueError, AttributeError):
            self._file_sort_refresh_at = now + 5.0
            preference = ('modified', True)
        if preference == self.file_sort:
            return False
        # Work on a private copy; queued results bind to this exact list/session.
        source = self.files
        identity = self._file_sort_identity()
        def resort():
            files = list(source)
            self._sort_files(files, preference=preference)
            return files, tuple(item['path'] for item in files)
        self._file_sort_pending = (identity, preference, self._read_worker.submit(resort))
        return self._poll_file_sort(now)

    def _sort_files(self, entries=None, preference=None):
        items = self.files if entries is None else entries
        field, descending = self.file_sort if preference is None else preference
        # Deterministic ties and full paths preserve distinct nested files.
        items.sort(key=lambda item: (item['path'].casefold(), item['path']))
        def value(item):
            if field == 'filename':
                return item['path'].rstrip('/').rsplit('/', 1)[-1].casefold()
            number = item.get(field)
            if isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number):
                return (True, number)
            return (False, 0)
        items.sort(key=value, reverse=descending)

    def GetFiles(self, refresh=False):
        self.refresh_file_sort()
        if not self._files_loaded or refresh:
            if time.monotonic() < self._file_retry_at and not refresh:
                return self._files_paths_snapshot
            self._files_loaded = False
            self._files_loading = True
            try:
                preference = self.file_sort
                revision = self.state.file_revision
                def prepare():
                    files = self.getREST('/server/files/list')['result']
                    if not isinstance(files, list) or not all(
                            isinstance(item, dict) and isinstance(item.get('path'), str)
                            and item['path'] for item in files):
                        raise ValueError('Invalid file list')
                    paths = {item['path'] for item in files}
                    if len(paths) != len(files):
                        raise ValueError('Duplicate file paths')
                    self._sort_files(files, preference=preference)
                    keys = {item['path']: (item['path'], item.get('modified'), item.get('size'),
                            revision if item.get('modified') is None else None) for item in files}
                    return files, tuple(item['path'] for item in files), keys
                files, paths, keys = self._read('files', prepare,
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
        if not self._files_loaded or (key not in self._directory_cache
                                     and key != self._root_prefetch_unretained):
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
        # A snapshot stays unresolved through read failures and retry backoff.
        # Only a successful directory result (including empty) may clear this.
        self._directory_loading = True
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
            self._root_prefetch_unretained = None
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
                if not directory:
                    # A successful oversized root needs no further automatic
                    # prefetch in this revision. Keep only its identity, not data.
                    # Explicit GetDirectory calls still fetch and return paths.
                    self._root_prefetch_unretained = (
                        key if size > self.DIRECTORY_CACHE_BYTES else None)
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
            self._directory_loading = False
            return orders[key][1] if key in orders else paths
        except ReadPending:
            return ()
        except (MoonrakerError, KeyError, TypeError, ValueError) as error:
            self._directory_loading = True
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
            initial = spool.get('initial_weight')
            if initial is None:
                initial = (spool.get('filament') or {}).get('weight')
            initial = float(initial)
            if (not math.isfinite(remaining) or not math.isfinite(initial)
                    or initial <= 0 or remaining < 0):
                return None
            return math.ceil(max(0, min(100, remaining / initial * 100)))
        except (KeyError, TypeError, ValueError, AttributeError):
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
            # The native subscription publishes immutable per-object trees.
            # Legacy/test subscriptions retain the detached snapshot path.
            lifecycle_reader = getattr(self.subscription,'lifecycle',None)
            life = lifecycle_reader() if callable(lifecycle_reader) else None
            same_revision = (isinstance(life,dict) and self.state.ready
                             and life.get('state') == 'ready'
                             and life.get('epoch') == self.state.epoch
                             and life.get('revision') == self.state.revision)
            if same_revision:
                state = replace(self.state, file_revision=life.get('file_revision',self.state.file_revision))
            elif getattr(self.subscription, '_supports_immutable_state', None) is True:
                state = self.subscription.immutable_state()
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
            thermal['fan_speed'][0] = js_round(data['fan']['speed'] * 100) if caps.fan else 0
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
        self._note_maintenance_state(state)
        if state.file_revision != self._file_revision:
            self._files_loaded = False
            self._file_revision = state.file_revision
        self.thermalManager = thermal
        self.feedrate_percentage = js_round(speed_percent)
        self.flow_percentage = js_round(flow_percent)
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

    def pause_job(self, report_error=True):
        # Moonraker expects JSON object arguments, even for an empty POST.
        return self.postREST('/printer/print/pause', json={},
                             report_error=report_error)

    def resume_job(self, report_error=True):
        if self.jog_recovery_required:
            raise ValueError('Restore jog state before resuming')
        return self.postREST('/printer/print/resume', json={},
                             report_error=report_error)

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
        return value > 0, js_round(value * 100)

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


