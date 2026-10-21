"""Single persistent direct-libnfc owner; keep only the latest card and identity."""
import logging
from threading import Event, Lock, Thread

from libnfc_api import NFCSession


class RFIDReader:
    def __init__(self):
        self._stop = Event()
        self._lock = Lock()
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

    def _run(self):
        while not self._stop.is_set():
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
                while not self._stop.is_set():
                    for modulation in session.modulations:
                        candidates = ((preferred, modulation)
                                      if preferred and preferred != modulation
                                      else (modulation,))
                        for candidate in candidates:
                            if self._stop.is_set():
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
            # Backoff applies only to reader failures, never normal scans.
            self._stop.wait(2)

    def close(self):
        self._stop.set()
        with self._lock:
            if self._session is not None:
                self._session.abort()
        self._thread.join(timeout=3)
