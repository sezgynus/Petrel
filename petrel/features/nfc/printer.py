"""Existing PrinterData methods grouped by responsibility."""
from concurrent.futures import Future
from petrel.features.nfc.reader import RFIDReader
from petrel.features.nfc.core import NFCCore
from petrel.features.nfc.settings import installed_enabled


class NFCPrinterMixin:
    def discover_serial_ports(self):
        """Fetch Moonraker's canonical UART list once, off the LCD UI thread."""
        from petrel.features.nfc.settings import serial_ports_from_moonraker
        return self._read_worker.submit(lambda: serial_ports_from_moonraker(
            self.client.get('/machine/peripherals/serial')))

    def discover_nfc_devices(self, model, interface):
        """Serialized hardware discovery; nonblocking for the LCD thread."""
        core = self.get_nfc_core()
        if core is None:
            future = Future()
            future.set_exception(OSError('NFC disabled'))
            return future
        return core.discover_devices(model, interface)

    def get_nfc_core(self):
        """Only one NFC Core and backend for all UI states."""
        if not installed_enabled():
            return None
        core = getattr(self, '_nfc_core', None)
        if core is not None:
            return core
        reader = getattr(self, '_rfid_reader', None)
        if reader is None:
            reader = self._rfid_reader = RFIDReader()
        core = NFCCore(reader, emergency_stop=lambda:
                       self.subscription.request('printer.emergency_stop'),
                       serial_devices=self.discover_serial_ports)
        self._nfc_core = core
        return core

    @staticmethod
    def _nfc_capability_label(value):
        return 'Yes' if value is True else 'No' if value is False else 'Unknown'

    def sync_nfc_event(self):
        """Called by an NFC event on the LCD owner, never on a timer."""
        core = self.get_nfc_core()
        if core is None:
            identity = {'status': 'Disabled'}
            values = {'status': 'Disabled', 'card': {}}
            old = (self.system_info.get('nfc'), self.system_info.get('rfid'))
            self.system_info['nfc'], self.system_info['rfid'] = identity, values
            return old != (identity, values)
        identity = core.get_reader_info()
        identity['ndef_uri'] = self._nfc_capability_label(
            core.get_capabilities().get('ndef_uri_emulation'))
        values = {'status': core.get_status(),
                  'card': core.get_last_card() or {}}
        old = (self.system_info.get('nfc'), self.system_info.get('rfid'))
        self.system_info['nfc'], self.system_info['rfid'] = identity, values
        return old != (identity, values)

    def nfc_lookup_spool(self, uid):
        """One on-arrival lookup, never a UI tick or libnfc operation."""
        from petrel.features.spoolman.tags import SpoolmanTags
        return self._read_worker.submit(
            lambda: SpoolmanTags(self.spoolman_client).lookup(uid))

    def nfc_spool_page(self, offset=0):
        """Load one Spoolman inventory page off the LCD/NFC workers."""
        from petrel.features.spoolman.tags import SpoolmanTags
        return self._read_worker.submit(
            lambda: SpoolmanTags(self.spoolman_client).page(offset))

    def nfc_assign_spool(self, spool, uid, approval=None):
        """Explicit confirmed server write; never activate/load the spool."""
        from petrel.features.spoolman.tags import SpoolmanTags
        core = self.get_nfc_core()
        if core is None:
            raise OSError('NFC disabled')
        from petrel.features.nfc.core import normalize_uid
        if core.global_action_uid('emergency_stop') == normalize_uid(uid):
            raise ValueError('Emergency tag cannot identify a spool')
        # One accepted tag write at a time; leaving its screen cannot enqueue
        # another move behind a still-running write.
        pending = getattr(self, '_nfc_spool_write', None)
        if isinstance(pending, Future) and not pending.done():
            raise OSError('Wait for the current spool tag write')
        future = self._read_worker.submit(
            lambda: SpoolmanTags(self.spoolman_client).assign(spool.id, uid, spool, approval))
        self._nfc_spool_write = future
        return future

    def test_nfc_connection(self, settings):
        """Queue a draft configuration probe through NFC Core."""
        core = self.get_nfc_core()
        if core is None:
            raise OSError('NFC feature disabled')
        settings.validate()
        return core.test_connection(settings)

    def reload_nfc_configuration(self):
        """Apply saved settings through the Core, never the LCD thread."""
        core = self.get_nfc_core()
        if core is None or not core.reload_configuration():
            raise OSError('NFC reader unavailable')
