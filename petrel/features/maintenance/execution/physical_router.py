"""Existing physical-operation routing across Maintenance domains."""
from petrel.features.maintenance.domains.thermal.controller import THERMAL_GROUP


class MaintenancePhysicalRouter:
    """One UI operation owner for pulse and thermal domains."""
    def __init__(self, pulse, heater, motion=None, switches=None, probe=None, resonance=None, filament=None, panel=None, auxiliary=None):
        self._pulse, self._heater = pulse, heater
        self._motion, self._switches, self._probe = motion, switches, probe
        self._resonance, self._filament, self._panel, self._auxiliary = resonance, filament, panel, auxiliary
        self._owners = tuple(x for x in (pulse, heater, motion, switches, probe, resonance, filament, panel, auxiliary) if x is not None)
        self._active = pulse

    def __getattr__(self, key):
        return getattr(self._active, key)

    @property
    def pending(self):
        return any(owner.pending for owner in self._owners)

    def available(self):
        rows = tuple(row for owner in self._owners for row in owner.available())
        # One visible thermal characterization entry per heater, while the
        # seven original discovery/catalog IDs remain independently tracked.
        grouped = {row.device for row in rows if row.feature_id == THERMAL_GROUP[0]}
        return tuple(row for row in rows if row.feature_id not in THERMAL_GROUP[1:]
                     or row.device not in grouped)

    def start(self, feature_id, device=None, **kwargs):
        if self.pending:
            return False, 'maintenance_busy'
        self._active = (self._auxiliary if feature_id in ('O01','O02','O06') else
                        self._panel if feature_id in ('S15','S16','S17') else
                        self._filament if feature_id.startswith('E') else
                        self._resonance if feature_id.startswith('R') else
                        self._probe if feature_id.startswith('P') else
                        self._switches if feature_id in ('M01', 'M10') else
                        self._motion if feature_id.startswith('M') else
                        self._heater if feature_id.startswith('H') else self._pulse)
        if self._active is None:
            self._active = self._pulse
            return False, 'motion_adapter_unavailable'
        return self._active.start(feature_id, device, **kwargs)

    def close(self):
        for owner in self._owners:
            owner.close()
