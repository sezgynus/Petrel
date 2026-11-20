"""Cached update observation and explicit update actions for Petrel."""
import logging
import math
import time
from collections.abc import Mapping
from concurrent.futures import CancelledError
from threading import Event
from petrel.moonraker.client import MoonrakerClient, MoonrakerError
from petrel.printer.background_reads import ReadPending, ReadWorker


class SoftwareUpdate:
    def __init__(self, printer, worker=None, *, check_interval=600.0):
        if not math.isfinite(check_interval) or check_interval <= 0:
            raise ValueError('Automatic update check interval must be positive')
        self.printer = printer
        self._worker = worker
        self._closed = Event()
        self.future = None
        self.phase = 'idle'
        self.message = ''
        self.name = None
        self.update_available = None
        self.confirm_epoch = None
        self._observed = None
        self._status_retry = (None, 0.0)
        self._action_generation = 0
        self._check_interval = check_interval
        self._next_automatic_check = 0.0
        self._automatic_check = None

    @property
    def label(self):
        return {'checking': 'Checking...', 'available': 'Update',
                'updating': 'Updating...', 'restarting': 'Restarting...',
                'dirty': 'Soft recovery', 'confirm_recovery': 'Confirm recovery',
                'recovering': 'Recovering...'}.get(
                    self.phase, 'Check for updates')

    def start(self):
        if (self._closed.is_set() or self.future is not None or self._automatic_check is not None
                or self.phase == 'restarting'):
            return
        printer = self.printer
        snapshot = printer.subscription.snapshot()
        if snapshot.get('state') != 'ready' or snapshot.get('status', {}).get('print_stats', {}).get('state') in ('printing', 'paused'):
            self.message = 'Printer must be idle'
            return
        if self.phase == 'dirty':
            self.phase = 'confirm_recovery'
            self.confirm_epoch = snapshot.get('epoch')
            self.message = 'Discard local changes? Press again'
            return
        recover = self.phase == 'confirm_recovery'
        if recover and snapshot.get('epoch') != self.confirm_epoch:
            self.cancel_confirmation()
            self.message = 'Printer state changed; check again'
            self.phase = 'error'
            return
        upgrade = self.phase == 'available'
        epoch = snapshot.get('epoch')
        name = self.name

        def work():
            # Update calls may take much longer than normal UI telemetry reads.
            client = MoonrakerClient(printer.client.url,
                                    printer.client.headers.get('X-Api-Key', ''), timeout=120)
            def ensure_open():
                if self._closed.is_set():
                    raise RuntimeError('Update observation closed; check Mainsail')
            def get(path):
                ensure_open()
                return client.get(path)
            def request(*args):
                ensure_open()
                return client.request(*args)
            try:
                ensure_open()
                current = printer.subscription.snapshot()
                if current.get('state') != 'ready' or current.get('epoch') != epoch or current.get('status', {}).get('print_stats', {}).get('state') in ('printing', 'paused'):
                    raise ValueError('Printer state changed')
                if recover:
                    versions = get('/machine/update/status')['result']['version_info']
                    item = versions.get(name, {})
                    if not name or name.casefold() != 'petrel' or not item or (item.get('is_valid', False) and not item.get('is_dirty', False)):
                        raise ValueError('Check updates again')
                    request('POST', '/machine/update/recover', {'name': name, 'hard': False})
                    refreshed = request('POST', '/machine/update/refresh', {'name': name})
                    item = refreshed['result']['version_info'][name]
                    if not item.get('is_valid', False) or item.get('is_dirty', False):
                        raise ValueError('Recovery incomplete; check Mainsail')
                    return name, self.available(item)
                if upgrade:
                    # Re-check validity and revision before installing a previously checked update.
                    versions = get('/machine/update/status')['result']['version_info']
                    item = versions.get(name, {})
                    if not self.available(item):
                        raise ValueError('Check updates again')
                    request('POST', '/machine/update/client', {'name': name})
                    return name, None
                versions = get('/machine/update/status')['result']['version_info']
                name_found = self._petrel_name(versions)
                if name_found is None:
                    raise ValueError('Updater not configured')
                refreshed = request('POST', '/machine/update/refresh', {'name': name_found})
                item = refreshed['result']['version_info'][name_found]
                if not item.get('is_valid', False) or item.get('is_dirty', False):
                    return name_found, 'dirty'
                return name_found, self.available(item)
            finally:
                client.close()

        self.phase = 'recovering' if recover else ('updating' if upgrade else 'checking')
        self._action_generation += 1
        self.message = 'Please wait...'
        self.future = self._submit(work)

    def _submit(self, work):
        if self._worker is None:
            self._worker = ReadWorker(timeout=1, capacity=1, queue_timeout=5)
        return self._worker.submit(work)

    @staticmethod
    def _petrel_name(versions):
        return next((key for key in versions if key.casefold() == 'petrel'), None)

    @staticmethod
    def _automatic_idle(snapshot):
        status = snapshot.get('status', {})
        return (snapshot.get('state') == 'ready'
                and status.get('print_stats', {}).get('state') in ('standby', 'complete', 'cancelled', 'error')
                and status.get('virtual_sdcard', {}).get('is_active') is not True
                and status.get('pause_resume', {}).get('is_paused') is not True
                and status.get('webhooks', {}).get('state', 'ready') == 'ready')

    def poll_automatic_check(self, print_start_pending):
        """Run a due refresh without changing the manual update button phase."""
        if self._closed.is_set():
            return
        now = time.monotonic()
        pending = self._automatic_check
        if pending is not None:
            if not pending.done():
                return
            self._automatic_check = None
            try:
                checked = pending.result()
                if checked is None:
                    self._next_automatic_check = now + min(15.0, self._check_interval)
                elif checked:
                    self._next_automatic_check = now + self._check_interval
            except Exception as error:
                # Moonraker can still be initializing or reject a print that
                # began between our last snapshot and the server admission.
                delay = self._check_interval
                if str(error) == 'Moonraker HTTP status 503':
                    delay = min(15.0, delay)
                self._next_automatic_check = now + delay
                logging.debug('Automatic Petrel update check failed: %s', error)
            return
        if (now < self._next_automatic_check or self.future is not None
                or self.phase in ('confirm_recovery', 'restarting') or print_start_pending()):
            return
        printer = self.printer
        snapshot = printer.subscription.snapshot(include_settings=False)
        if not self._automatic_idle(snapshot):
            return
        epoch = snapshot['epoch']

        def eligible():
            latest = printer.subscription.snapshot(include_settings=False)
            return (not self._closed.is_set() and not print_start_pending()
                    and latest.get('epoch') == epoch and self._automatic_idle(latest))

        def refresh():
            if not eligible():
                return False
            client = MoonrakerClient(printer.client.url,
                                     printer.client.headers.get('X-Api-Key', ''), timeout=120)
            try:
                result = client.get('/machine/update/status')['result']
                if result.get('busy'):
                    return None
                name = self._petrel_name(result['version_info'])
                if name is None:
                    return True
                if not eligible():
                    return False
                client.request('POST', '/machine/update/refresh', {'name': name})
                return True
            finally:
                client.close()

        self._automatic_check = self._submit(refresh)

    def cancel_confirmation(self):
        if self.phase == 'confirm_recovery':
            self.phase, self.message = 'dirty', 'Repo invalid or modified'
        self.confirm_epoch = None

    @staticmethod
    def available(item):
        return (item.get('is_valid', False) and not item.get('is_dirty', False)
                and bool(item.get('current_hash')) and bool(item.get('remote_hash'))
                and item['current_hash'] != item['remote_hash'])

    def observe(self):
        """Read Moonraker's cached result once per connection and update event."""
        if (self._closed.is_set() or self.future is not None
                or self.phase == 'confirm_recovery'):
            return False
        printer = self.printer
        life = printer.subscription.lifecycle()
        if not isinstance(life, Mapping) or life.get('state') != 'ready':
            return False
        stamp = (life['epoch'], life.get('update_revision', 0))
        retry_stamp, retry_at = self._status_retry
        if stamp == self._observed or (stamp == retry_stamp and time.monotonic() < retry_at):
            return False
        try:
            response = printer._read('petrel_update_status',
                                     lambda: printer.client.get('/machine/update/status'),
                                     stamp=(*stamp, self._action_generation))
            result = response['result']
            if result.get('busy'):
                self._status_retry = (stamp, time.monotonic() + 5.0)
                return False
            versions = result['version_info']
            name = self._petrel_name(versions)
            item = versions.get(name, {})
            available = self.available(item)
        except ReadPending:
            return False
        except (MoonrakerError, OSError, CancelledError, AttributeError, KeyError, TypeError, ValueError) as error:
            logging.debug('Cannot observe Petrel update status: %s', error)
            self._status_retry = (stamp, time.monotonic() + 30.0)
            return False
        latest = printer.subscription.lifecycle()
        if (latest.get('state') != 'ready'
                or stamp != (latest['epoch'], latest.get('update_revision', 0))):
            return False
        self._observed = stamp
        self.update_available = bool(available)
        previous = (self.phase, self.message)
        if self.phase == 'restarting':
            return False
        if available:
            self.name = name
            self.phase, self.message = 'available', 'Update available'
        elif self.phase == 'available':
            self.phase, self.message = 'idle', ''
        return previous != (self.phase, self.message)

    def poll(self):
        if self.future is None or not self.future.done():
            return False
        future, self.future = self.future, None
        try:
            self.name, available = future.result()
            if available is not None:
                self.update_available = available is True
            if available == 'dirty':
                self.phase, self.message = 'dirty', 'Repo invalid or modified'
            elif available is None:
                self.phase, self.message = 'restarting', 'Restarting Petrel'
            elif available:
                self.phase, self.message = 'available', 'Update available'
            else:
                self.phase, self.message = 'current', 'Up to date'
        except Exception as error:
            upgrading = self.phase == 'updating'
            recovering = self.phase == 'recovering'
            self.phase = 'error'
            self.message = ('Update unconfirmed; check Mainsail' if upgrading else
                            'Recovery unconfirmed; check Mainsail' if recovering else str(error))
        return True

    def close(self):
        # A submitted update may already execute remotely; never replay it.
        self._closed.set()
        if self.future is not None:
            self.future.cancel()
        if self._automatic_check is not None:
            self._automatic_check.cancel()
        if self._worker is not None:
            self._worker.close()
