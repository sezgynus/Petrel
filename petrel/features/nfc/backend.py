"""NFC backend: the sole libnfc hardware owner inside Petrel.

The backend runs in one worker thread. It owns every libnfc context/device,
serializes connection probes with scans, and applies saved configuration only
between fully closed sessions. The UI and future NFC Core never touch libnfc.
"""
import logging
from concurrent.futures import Future
from threading import Event, Lock, Thread

from petrel.features.nfc.libnfc import NFCSession, NFCTargetSession, check_connection
from petrel.features.nfc.ndef import ndef_uri_file
from petrel.features.nfc.settings import PROFILES, available_ports, installed_enabled, load


class NFCBackend:
    def __init__(self, *, feature_enabled=None, config_loader=None,
                 session_factory=None, probe_factory=None, retry_seconds=2,
                 target_factory=None):
        # Inject factories for CI without opening physical devices.
        self._feature_enabled = feature_enabled or installed_enabled
        self._config_loader = config_loader or load
        self._session_factory = session_factory
        self._probe_factory = probe_factory
        self._retry_seconds = retry_seconds
        self._target_factory = target_factory
        self._target_session = None
        self._share = None
        self._share_active = False
        self._share_event = Event()
        self._share_cancel = Event()
        self._discover = None
        self._discover_event = Event()
        self._sink = None
        self._capabilities = {'target_mode': None, 'ndef_uri_emulation': None}
        self._settings = None
        self._change = Event()
        self._change.set()  # Read disk once on backend startup.
        self._wake = Event()
        self._stop = Event()
        self._lock = Lock()
        self._probe_event = Event()
        self._probe = None
        self._probe_active = False
        self._session = None
        self._card = {}
        self._present_card = None
        self._present_modulation = None
        self._missing_reads = 0
        self._card_event = False
        self._identity = {'status': 'Unavailable'}
        self._status = 'Starting...'
        self._revision = 0
        self._thread = Thread(target=self._run, name='petrel-nfc-backend', daemon=True)
        self._thread.start()

    def set_event_sink(self, callback):
        with self._lock:
            self._sink = callback

    def _emit(self, event, data):
        with self._lock:
            callback = self._sink
        if callback is not None:
            try:
                callback(event, dict(data))
            except Exception:
                logging.exception('NFC event sink failed')

    def _interrupt_scan(self):
        """Ask libnfc to end an in-flight scan so queued work runs promptly.

        Do not close or open a device here. Only the worker may do that, after
        the interrupted scan has unwound. Synchronize with session teardown.
        """
        with self._lock:
            if self._session is not None:
                try:
                    self._session.abort()
                except Exception:
                    logging.exception('Unable to interrupt NFC scan')

    def capabilities(self):
        with self._lock:
            return dict(self._capabilities)

    def share_ndef_uri(self, url):
        """Queue target mode, without occupying the UI or scanner threads."""
        ndef_uri_file(url)
        future = Future()
        with self._lock:
            if self._stop.is_set() or not self._feature_enabled():
                future.set_exception(OSError('NFC unavailable'))
            elif self._capabilities.get('ndef_uri_emulation') is not True:
                future.set_exception(OSError('NDEF URI emulation unsupported or unknown'))
            elif self._share_active or self._share is not None:
                future.set_exception(OSError('NFC share already active'))
            else:
                self._share = (url, future)
                self._share_cancel.clear()
                self._share_event.set()
                self._wake.set()
        if not future.done():
            self._interrupt_scan()
        return future

    def cancel_share(self):
        with self._lock:
            pending = self._share
            if pending is None and not self._share_active:
                return False
            self._share_cancel.set()
            target = self._target_session
            self._wake.set()
            if pending is not None and not self._share_active:
                self._share = None
                self._share_event.clear()
                pending[1].cancel()
        if pending is not None and not self._share_active:
            self._emit('share.cancelled', {})
        if target is not None:
            target.abort()
        return True

    def discover_devices(self, model, interface):
        """All on-demand libnfc enumeration happens on the hardware owner."""
        if model not in PROFILES or interface not in PROFILES[model]['interfaces']:
            raise ValueError('Unsupported NFC reader/transport')
        future = Future()
        with self._lock:
            if not self._feature_enabled():
                future.set_exception(OSError('NFC feature disabled'))
            elif self._stop.is_set():
                future.set_exception(OSError('NFC backend stopped'))
            elif self._discover is not None:
                future.set_exception(OSError('NFC discovery busy'))
            else:
                self._discover = (model, interface, future)
                self._discover_event.set()
                self._wake.set()
        if not future.done():
            self._interrupt_scan()
        return future

    def _run_discovery(self):
        with self._lock:
            pending, self._discover = self._discover, None
            self._discover_event.clear()
        if pending is None:
            return
        model, interface, future = pending
        if not future.set_running_or_notify_cancel():
            return
        try:
            if interface in ('USB', 'PC/SC', 'NCI'):
                from petrel.features.nfc.libnfc import list_devices
                prefix = PROFILES[model]['drivers'][interface] + ':'
                paths = tuple(device for device in list_devices()
                              if device.startswith(prefix))
            else:
                paths = available_ports(interface, model)
            future.set_result(paths)
        except Exception as error:
            future.set_exception(error)

    def snapshot(self):
        with self._lock:
            return self._revision, self._status, dict(self._card)

    def identity(self):
        with self._lock:
            return dict(self._identity)

    def take_card_event(self):
        """Consume a bounded arrival notification without changing the last card."""
        with self._lock:
            event, self._card_event = self._card_event, False
            return event

    def _observe_card(self, modulation, card):
        event, payload = None, {}
        with self._lock:
            if card:
                key = (card.get('type'), card['uid'])
                if key != self._present_card:
                    self._card_event = True
                    event, payload = 'card.detected', dict(card)
                self._present_card = key
                self._present_modulation = modulation
                self._missing_reads = 0
            elif modulation == self._present_modulation:
                # Other technologies missing this card do not mean removal.
                self._missing_reads += 1
                if self._missing_reads >= 2:
                    event, payload = 'card.removed', {'type': self._present_card[0],
                                                       'uid': self._present_card[1]}
                    self._present_card = None
                    self._present_modulation = None
        if event is not None:
            self._emit(event, payload)

    def _publish(self, status, card=None, identity=None):
        notification = None
        with self._lock:
            latest = card if card and card.get('uid') else self._card
            info = identity if identity is not None else self._identity
            if status != self._status or latest != self._card or info != self._identity:
                self._status, self._card, self._identity = status, dict(latest), dict(info)
                self._revision += 1
                notification = {'status': status, 'identity': dict(info)}
        if notification is not None:
            self._emit('reader.changed', notification)

    def test_connection(self, settings):
        """Test the unsaved draft on the hardware owner, never the UI thread."""
        settings.validate()
        future = Future()
        with self._lock:
            if not self._feature_enabled():
                future.set_exception(OSError('NFC feature disabled'))
            elif self._stop.is_set():
                future.set_exception(OSError('NFC reader stopped'))
            elif self._probe_active:
                future.set_exception(OSError('NFC test already in progress'))
            else:
                self._probe_active = True
                self._probe = (settings, future)
                self._probe_event.set()
                self._wake.set()
        if not future.done():
            self._interrupt_scan()
        return future

    def reload_configuration(self):
        """Apply a newly saved file after the active scan session closes."""
        self.cancel_share()
        with self._lock:
            if self._stop.is_set():
                return False
            self._change.set()
            self._wake.set()
        self._interrupt_scan()
        return True

    def _read_configuration(self):
        """Resolve only the saved, validated configuration; never a UART fallback."""
        if not self._feature_enabled():
            self._reset_for_configuration('Disabled')
            return None
        try:
            settings = self._config_loader().validate()
        except (OSError, ValueError, TypeError) as error:
            logging.info('NFC reader not configured: %s', error)
            self._reset_for_configuration('Not configured')
            return None
        self._reset_for_configuration('Starting...')
        return settings

    def _reset_for_configuration(self, status):
        removed = None
        with self._lock:
            if self._present_card is not None:
                removed = {'type': self._present_card[0],
                           'uid': self._present_card[1]}
            self._card = {}
            self._present_card = None
            self._present_modulation = None
            self._missing_reads = 0
            self._card_event = False
            self._identity = {'status': 'Unavailable'}
            self._status = status
            self._capabilities = {'target_mode': None, 'ndef_uri_emulation': None}
            self._revision += 1
        if removed is not None:
            self._emit('card.removed', removed)
        self._emit('capabilities.changed', self.capabilities())
        self._emit('reader.changed', {'status': status, 'identity': {'status': 'Unavailable'}})

    def _run_probe(self):
        with self._lock:
            pending, self._probe = self._probe, None
            self._probe_event.clear()
        if pending is None:
            return False
        settings, future = pending
        try:
            if future.set_running_or_notify_cancel():
                try:
                    tester = self._probe_factory or check_connection
                    future.set_result(tester(settings))
                except Exception as error:
                    future.set_exception(error)
        finally:
            with self._lock:
                self._probe_active = False
        return True

    def _run_share(self):
        with self._lock:
            pending, self._share = self._share, None
            self._share_event.clear()
            self._share_active = pending is not None
            # Target-mode sharing suspends detection. Force a fresh
            # card presentation when the initiator resumes.
            self._present_card = None
            self._present_modulation = None
            self._missing_reads = 0
        if pending is None:
            return
        url, future = pending
        target = None
        try:
            if not future.set_running_or_notify_cancel():
                return
            if self._share_cancel.is_set():
                future.set_result(False)
                return
            factory = self._target_factory or NFCTargetSession
            target = factory(self._settings)
            with self._lock:
                self._target_session = target
            self._publish('Sharing')
            self._emit('share.started', {'url': url})
            success = target.serve_uri(
                url, lambda: self._stop.is_set() or self._share_cancel.is_set(), self._emit)
            if not future.done():
                future.set_result(bool(success))
            if not success:
                self._emit('share.cancelled', {})
        except Exception as error:
            if self._share_cancel.is_set() or self._stop.is_set():
                if not future.done():
                    future.set_result(False)
                self._emit('share.cancelled', {})
            else:
                logging.warning('NFC URI share failed: %s', error)
                if not future.done():
                    future.set_exception(error)
                self._emit('share.failed', {'reason': str(error)})
        finally:
            with self._lock:
                self._target_session = None
            if target is not None:
                target.close()
            with self._lock:
                self._share_active = False
            self._share_cancel.clear()

    def _run(self):
        while not self._stop.is_set():
            # Commands have priority; a probe must never overlap scanning.
            if self._probe_event.is_set():
                self._run_probe()
                continue
            if self._discover_event.is_set():
                self._run_discovery()
                continue
            if self._change.is_set():
                self._change.clear()
                self._settings = self._read_configuration()
            if self._share_event.is_set() and self._settings is not None:
                self._run_share()
                continue
            if self._settings is None:
                # No busy polling, no attempt to occupy DWIN's default port.
                self._wake.wait()
                self._wake.clear()
                continue
            session = None
            try:
                factory = self._session_factory or NFCSession
                session = factory(self._settings)
                with self._lock:
                    if self._stop.is_set():
                        break
                    self._session = session
                self._publish('Listening', identity=session.identity())
                caps = session.capabilities() if callable(getattr(session, 'capabilities', None)) else None
                if isinstance(caps, dict):
                    with self._lock:
                        self._capabilities = dict(caps)
                    self._emit('capabilities.changed', caps)
                unsupported = set()
                # Start with Type A when available, then follow the most recent
                # successful technology. Revisit it between every other scan,
                # while advancing all advertised technologies fairly in order.
                preferred = (1, 1) if (1, 1) in session.modulations else None
                while (not self._stop.is_set() and not self._probe_event.is_set()
                       and not self._change.is_set() and not self._share_event.is_set()
                       and not self._discover_event.is_set()):
                    for modulation in session.modulations:
                        if (self._probe_event.is_set() or self._change.is_set()
                                or self._share_event.is_set() or self._discover_event.is_set()):
                            break
                        candidates = ((preferred, modulation)
                                      if preferred and preferred != modulation
                                      else (modulation,))
                        for candidate in candidates:
                            if (self._stop.is_set() or self._probe_event.is_set()
                                    or self._change.is_set() or self._share_event.is_set()
                                    or self._discover_event.is_set()):
                                break
                            if candidate in unsupported:
                                continue
                            card = session.scan(candidate)
                            if card != 'unsupported':
                                self._observe_card(candidate, card)
                            if card == 'unsupported':
                                unsupported.add(candidate)
                                logging.warning('NFC reader rejected advertised modulation %s', candidate)
                                self._publish('Partial support')
                            elif card:
                                preferred = candidate
                                self._publish('Partial support' if unsupported else 'Listening', card)
                        if self._stop.is_set():
                            break
                    if len(unsupported) == len(session.modulations):
                        raise OSError('No usable NFC modulation')
            except (OSError, ValueError) as error:
                # nfc_abort_command() can terminate a scan with a libnfc
                # error. That is not a reader failure if a command requested
                # the interruption: process it after closing this session.
                preempted = (self._probe_event.is_set() or self._discover_event.is_set()
                             or self._change.is_set() or self._share_event.is_set())
                if not self._stop.is_set() and not preempted:
                    logging.warning('NFC reader unavailable: %s', error)
                    # A reconnect must count the same UID as a new arrival.
                    # Never keep a stale pending arrival after unplug/errors.
                    self._reset_for_configuration('Reader unavailable')
            finally:
                with self._lock:
                    self._session = None
                if session is not None:
                    session.close()
            # Saved configuration and explicit probes take precedence over
            # failure backoff. Idle devices have a bounded reconnect interval.
            if (not self._stop.is_set() and not self._change.is_set()
                    and not self._probe_event.is_set() and not self._share_event.is_set()
                    and not self._discover_event.is_set()):
                self._wake.wait(self._retry_seconds)
                self._wake.clear()

    def close(self):
        self._stop.set()
        self.cancel_share()
        self._wake.set()
        with self._lock:
            pending, self._discover = self._discover, None
            if pending is not None:
                pending[2].cancel()
        with self._lock:
            pending, self._probe = self._probe, None
            if pending is not None:
                pending[1].cancel()
        with self._lock:
            if self._session is not None:
                self._session.abort()
            if self._target_session is not None:
                self._target_session.abort()
        self._thread.join(timeout=3)
        # No second backend may claim this reader while close is unfinished.
        return not self._thread.is_alive()
