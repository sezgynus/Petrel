"""Existing PrinterData methods grouped by responsibility."""
from petrel.features.printing.estimates import progress as print_progress, estimates as print_estimates, number as time_number
import logging
import math
import time
from urllib.parse import quote
from collections.abc import Mapping
from concurrent.futures import Future
from petrel.printer.background_reads import ReadPending
from petrel.printer.operation_guards import idle_dispatch_guard
from petrel.moonraker.client import MoonrakerError


class PrintingPrinterMixin:
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
        # An external client can start a job after selection but before the
        # queued HTTP request leaves MoonrakerClient.
        return self.postREST('/printer/print/start', json={'filename': path},
                             dispatch_guard=idle_dispatch_guard(self))

    def print_job_identity(self):
        """Stable for a print despite status updates; changes across observed jobs."""
        snap = self.subscription.snapshot()
        stats = snap.get('status', {}).get('print_stats', {})
        if (snap.get('state') != 'ready'
                or stats.get('state') not in ('printing', 'paused', 'pausing')):
            return None
        epoch = snap.get('epoch')
        generation = snap.get('print_job_generation')
        filename = stats.get('filename')
        if (type(epoch) is not int or epoch < 0
                or type(generation) is not int or generation < 1
                or not isinstance(filename, str) or not filename):
            return None
        # Duration telemetry can be corrected within a single print.
        return (epoch, generation, filename)

    def print_job_matches(self, identity):
        current = self.print_job_identity()
        return identity is not None and current is not None and identity == current

    def cancel_job(self, expected_job=None):
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
        if expected_job is not None and not self.print_job_matches(expected_job):
            future = Future()
            future.set_exception(ValueError('Print job changed; cancel rejected'))
            return future

        def still_same_job():
            current = self.subscription.snapshot()
            stats = current['status'].get('print_stats', {})
            return (current['state'] == 'ready' and current['epoch'] == epoch
                    and stats.get('filename') == filename
                    and stats.get('state') in ('printing', 'paused', 'pausing')
                    and (expected_job is None or self.print_job_matches(expected_job)))

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
        from petrel.features.printing.tuning import settings
        return settings(self)

    def set_print_setting(self, key, value, report_error=True, expected_job=None):
        from petrel.features.printing.tuning import set_value
        return set_value(self, key, value, report_error=report_error,
                         expected_job=expected_job)

    def print_layers(self):
        from petrel.features.printing.tuning import layers
        return layers(self)

    def set_feedrate(self, fr, report_error=True, dispatch_guard=None):
        fr = float(fr)
        if not math.isfinite(fr) or fr <= 0:
            raise ValueError('Feedrate percentage must be positive')
        script = 'M220 S{:g}'.format(fr)
        if dispatch_guard is not None:
            return self.sendGCode(script, report_error=report_error,
                                  dispatch_guard=dispatch_guard)
        return self.sendGCode(script) if report_error else self.sendGCode(script, report_error=False)
