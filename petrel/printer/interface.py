"""Own printer sessions, workers, telemetry and command transport."""
from petrel.features.nfc.printer import NFCPrinterMixin
from petrel.features.info.printer import InfoPrinterMixin
from petrel.features.maintenance.printer import MaintenancePrinterMixin
from petrel.features.files.printer import FilePrinterMixin
from petrel.features.spoolman.printer import SpoolmanPrinterMixin
from petrel.features.printing.printer import PrintingPrinterMixin
from petrel.features.motion.printer import MotionPrinterMixin
from petrel.features.temperature.printer import TemperaturePrinterMixin
from petrel.features.power.printer import PowerPrinterMixin
from petrel.features.case_light.printer import CaseLightPrinterMixin
from petrel.printer.models import xyze_t, AxisEnum, HMI_value_t, HMI_Flag_t, buzz_t, material_preset_t
from petrel.features.recovery.klipper import KlipperRecovery
import copy
from dataclasses import replace
import logging
import math
import time
import uuid
from collections.abc import Mapping
from concurrent.futures import Future
from threading import Lock
from petrel.ui.numbers import js_round
from petrel.printer.background_reads import ReadWorker, ReadPending
from petrel.printer.operation_guards import motion_dispatch_guard, idle_dispatch_guard
from petrel.moonraker.client import MoonrakerClient, MoonrakerError
from petrel.moonraker.subscription import MoonrakerSubscription
from petrel.features.leveling.probe_wizard import ProbeWizard
from petrel.features.leveling.screws_tilt import ScrewsTiltSession
from petrel.features.leveling.bed_mesh import BedMeshSession
from petrel.features.mmu.state import MMUSession
from petrel.features.temperature.preset_store import PresetStore
from petrel.printer.state import PrinterState
from petrel.printer.capabilities import PrinterCapabilities
from petrel.features.maintenance.discovery.session import MaintenanceDiscoveryManager
from petrel.features.maintenance.execution.controller import MaintenanceReadController
from petrel.features.maintenance.domains.switches import MaintenanceSwitchController
from petrel.features.maintenance.domains.motion.controller import MaintenanceMotionController
from petrel.features.maintenance.domains.probe import MaintenanceProbeController
from petrel.features.maintenance.domains.resonance import MaintenanceResonanceController
from petrel.features.maintenance.domains.filament.controller import MaintenanceFilamentController
from petrel.features.maintenance.domains.panel import MaintenancePanelController
from petrel.features.maintenance.domains.auxiliary.controller import MaintenanceAuxiliaryController
from petrel.features.maintenance.records.book import MaintenanceBook
from petrel.features.maintenance.assessment.service import MaintenanceAssessment
from petrel.features.maintenance.domains.pulse.controller import MaintenancePulseController
from petrel.features.maintenance.domains.thermal.controller import MaintenanceHeaterController, MaintenancePhysicalRouter


class PrinterData(
    NFCPrinterMixin,
    InfoPrinterMixin,
    MaintenancePrinterMixin,
    FilePrinterMixin,
    SpoolmanPrinterMixin,
    PrintingPrinterMixin,
    MotionPrinterMixin,
    TemperaturePrinterMixin,
    PowerPrinterMixin,
    CaseLightPrinterMixin,
):
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
        self.client.script_dispatch_callback = self._script_sound_dispatch
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
        core = getattr(self, '_nfc_core', None)
        if core is not None:
            core.close()
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
        # Read workers are daemon threads. Normal process exit must also wait
        # for an already-started multi-request tag write, not merely retain its
        # HTTP client. Queued work has been cancelled by close above.
        write = getattr(self, '_nfc_spool_write', None)
        if isinstance(write, Future) and write.running():
            try:
                write.result(timeout=60.0)
            except TimeoutError:
                logging.error('Spoolman tag write unfinished at shutdown; check Spoolman Tags')
            except Exception:
                logging.warning('Spoolman tag write failed during shutdown; check Spoolman Tags')
        self._maintenance_worker.close()
        self.maintenance_book.close()
        # A started tag move may span several HTTP calls. Keep its transport
        # alive until the owning worker has finished, even if close timed out.
        if callable(getattr(type(self._read_worker), 'on_stopped', None)):
            self._read_worker.on_stopped(self.spoolman_client.close)
        else:
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


    # END TEMPORARY MAINTENANCE TEST TRACE


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


    def init_Webservices(self):
        # Bootstrap and reconnection run on the subscription thread.
        return self.update_variable()


    DIRECTORY_CACHE_BYTES = 2 * 1024 * 1024


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

    def _script_sound_dispatch(self, script):
        from petrel.features.buzzer.notifications import contains_homing, emit_operation
        if contains_homing(script):
            emit_operation(self, 'HOMING', self.state.epoch)

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

    def _send_control_gcode(self, script, *, report_error=True, idle_only=False,
                            dispatch_guard=None):
        guard = dispatch_guard
        if idle_only:
            idle_guard = idle_dispatch_guard(self)
            guard = ((lambda: idle_guard() and dispatch_guard())
                     if dispatch_guard is not None else idle_guard)
        if guard is not None:
            return self.sendGCode(script, report_error=report_error,
                                  dispatch_guard=guard)
        if report_error:
            return self.sendGCode(script)
        return self.sendGCode(script, report_error=False)


