"""Single persistent direct-libnfc owner; keep only the latest card and identity."""
import logging
from concurrent.futures import Future
from threading import Event, Lock, Thread

from libnfc_api import NFCSession, check_connection


class RFIDReader:
    def __init__(self):
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
        self._identity = {'status': 'Reading...'}
        self._status = 'Starting...'
        self._revision = 0
        self._thread = Thread(target=self._run, name='petrel-rfid', daemon=True)
        self._thread.start()

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
        with self._lock:
            if card:
                key = (card.get('type'), card['uid'])
                if key != self._present_card:
                    self._card_event = True
                self._present_card = key
                self._present_modulation = modulation
                self._missing_reads = 0
            elif modulation == self._present_modulation:
                # Other technologies missing this card do not mean removal.
                self._missing_reads += 1
                if self._missing_reads >= 2:
                    self._present_card = None
                    self._present_modulation = None

    def _publish(self, status, card=None, identity=None):
        with self._lock:
            latest = card if card and card.get('uid') else self._card
            info = identity if identity is not None else self._identity
            if status != self._status or latest != self._card or info != self._identity:
                self._status, self._card, self._identity = status, dict(latest), dict(info)
                self._revision += 1

    def test_connection(self, settings):
        """Queue one exclusive reader probe; never open libnfc from the UI."""
        settings.validate()
        future = Future()
        with self._lock:
            if self._stop.is_set():
                future.set_exception(OSError('NFC reader stopped'))
            elif self._probe_active:
                future.set_exception(OSError('NFC test already in progress'))
            else:
                self._probe_active = True
                self._probe = (settings, future)
                self._probe_event.set()
        return future

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
                    future.set_result(check_connection(settings))
                except Exception as error:
                    future.set_exception(error)
        finally:
            with self._lock:
                self._probe_active = False
        return True

    def _run(self):
        while not self._stop.is_set():
            if self._probe_event.is_set():
                self._run_probe()
                continue
            session = None
            try:
                session = NFCSession()
                with self._lock:
                    if self._stop.is_set():
                        break
                    self._session = session
                self._publish('Listening', identity=session.identity())
                unsupported = set()
                # Start with Type A when available, then follow the most recent
                # successful technology. Revisit it between every other scan,
                # while advancing all advertised technologies fairly in order.
                preferred = (1, 1) if (1, 1) in session.modulations else None
                while not self._stop.is_set() and not self._probe_event.is_set():
                    for modulation in session.modulations:
                        if self._probe_event.is_set():
                            break
                        candidates = ((preferred, modulation)
                                      if preferred and preferred != modulation
                                      else (modulation,))
                        for candidate in candidates:
                            if self._stop.is_set() or self._probe_event.is_set():
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
                if not self._stop.is_set():
                    logging.warning('NFC reader unavailable: %s', error)
                    self._publish('Reader unavailable', identity={'status': 'Unavailable'})
            finally:
                with self._lock:
                    self._session = None
                if session is not None:
                    session.close()
            # A requested probe interrupts between scans and skips backoff.
            if not self._probe_event.is_set():
                self._probe_event.wait(2)

    def close(self):
        self._stop.set()
        self._probe_event.set()
        with self._lock:
            pending, self._probe = self._probe, None
            if pending is not None:
                pending[1].cancel()
        with self._lock:
            if self._session is not None:
                self._session.abort()
        self._thread.join(timeout=3)
