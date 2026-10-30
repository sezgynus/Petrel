"""Existing PrinterData methods grouped by responsibility."""
from petrel.moonraker.client import MoonrakerError


class PowerPrinterMixin:
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
