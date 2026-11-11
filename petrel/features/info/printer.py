"""Existing PrinterData methods grouped by responsibility."""
import logging
import math
import time
from collections.abc import Mapping
from concurrent.futures import CancelledError
from petrel.printer.background_reads import ReadPending
from petrel.moonraker.client import MoonrakerError
from petrel.features.info.system import host_memory_usage, host_metrics, network_info, updater_version, wifi_info


class InfoPrinterMixin:
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
