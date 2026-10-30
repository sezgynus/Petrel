"""Existing PrinterData methods grouped by responsibility."""
from petrel.printer.models import material_preset_t
import copy
import logging
import math
import time
from collections.abc import Mapping
from petrel.printer.background_reads import ReadPending
from petrel.moonraker.client import MoonrakerError


class TemperaturePrinterMixin:
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

    def disable_all_heaters(self):
        if not self.capabilities.has_heaters:
            return None
        return self.sendGCode('TURN_OFF_HEATERS')

    def cooldown(self, idle_only=False):
        commands = []
        if self.capabilities.has_heaters:
            commands.append('TURN_OFF_HEATERS')
        if self.capabilities.fan:
            commands.append(self._fan_command(0))
        if commands:
            return self._send_control_gcode('\n'.join(commands), idle_only=idle_only)

    def zero_fan_speeds(self):
        if self.HAS_FAN:
            return self.setFanSpeed(0)

    @staticmethod
    def _fan_command(percent):
        percent = float(percent)
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError('Fan speed is out of range')
        return 'M106 S{:g}'.format(percent * 255 / 100)

    def setFanSpeed(self, percent, report_error=True, idle_only=False, dispatch_guard=None):
        if not self.HAS_FAN:
            raise ValueError('Fan is unavailable')
        send = lambda script: self._send_control_gcode(script, report_error=report_error, idle_only=idle_only, dispatch_guard=dispatch_guard)
        return send(self._fan_command(percent))

    def preheat(self, profile):
        preset = next((item for item in self.material_preset if item.name == profile), None)
        if preset is None:
            raise ValueError('Unknown preheat profile')
        return self.preHeat(preset.bed_temp, preset.hotend_temp)

    def preheat_preset(self, index, idle_only=False):
        if not isinstance(index, int) or not 0 <= index < len(self.material_preset):
            raise ValueError('Unknown preheat preset')
        preset = self.material_preset[index]
        return self.preHeat(preset.bed_temp, preset.hotend_temp, **({'idle_only': True} if idle_only else {}))

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

    def setExtTemp(self, target, toolnum=None, report_error=True, idle_only=False, dispatch_guard=None):
        heater = self.capabilities.active_hotend
        if toolnum is not None:
            name = 'extruder' + (str(toolnum) if toolnum else '')
            heater = next((item for item in self.capabilities.hotends if item.name == name), None)
        if heater is None:
            raise ValueError('Hotend is unavailable')
        value = heater.validate_target(target)
        send = lambda script: self._send_control_gcode(script, report_error=report_error, idle_only=idle_only, dispatch_guard=dispatch_guard)
        return send('SET_HEATER_TEMPERATURE HEATER={} TARGET={:g}'.format(heater.name, value))

    def setBedTemp(self, target, report_error=True, idle_only=False, dispatch_guard=None):
        heater = self.capabilities.bed
        if heater is None:
            raise ValueError('Heated bed is unavailable')
        value = heater.validate_target(target)
        send = lambda script: self._send_control_gcode(script, report_error=report_error, idle_only=idle_only, dispatch_guard=dispatch_guard)
        return send('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={:g}'.format(value))

    def preHeat(self, bedtemp, exttemp, toolnum=None, fan_speed=None, idle_only=False):
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
            return self._send_control_gcode('\n'.join(commands), idle_only=idle_only)
