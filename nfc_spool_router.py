"""Bounded event-driven spool lookup below enrollment and emergency priority."""
from concurrent.futures import Future
import logging
from threading import RLock

from nfc_core import normalize_uid


class NFCSpoolRouter:
    def __init__(self, core, lookup, on_ready):
        self.core, self.lookup, self.on_ready = core, lookup, on_ready
        self.lock = RLock()
        self.closed = False
        self.serial = 0
        self.active = None
        self.next = None
        self.result = None
        self.tokens = (
            core.subscribe('card.detected', self._card, priority=50),
            core.subscribe('action.emergency_stop', self._emergency))

    def _card(self, card):
        try:
            uid = normalize_uid(card.get('uid'))
        except (ValueError, TypeError):
            return False
        with self.lock:
            if self.closed:
                return False
            self.serial += 1
            self.next = (self.serial, uid)
            self.result = None
            if self.active is None:
                self._start()
        return False  # Card UI refresh is independent; sound waits for this result.

    def _start(self):
        serial, uid = self.next
        self.next = None
        try:
            future = self.lookup(uid)
        except Exception as error:
            future = Future()
            future.set_exception(error)
        self.active = future
        future.add_done_callback(lambda completed: self._done(serial, uid, completed))

    def _done(self, serial, uid, future):
        notify = False
        with self.lock:
            self.active = None
            if self.closed:
                return
            if serial == self.serial:
                try:
                    spool = future.result()
                except Exception as error:
                    logging.info('NFC spool lookup unavailable: %s', error)
                    spool = None
                self.result = (uid, spool)
                notify = True
            if self.next is not None:
                self._start()
        if notify:
            self.on_ready()

    def _emergency(self, card):
        with self.lock:
            self.serial += 1
            self.next = None
            self.result = (None, None)
        self.on_ready()
        return False

    def take_result(self):
        with self.lock:
            value, self.result = self.result, None
            return value

    def close(self):
        with self.lock:
            self.closed = True
            self.serial += 1
            self.result = self.next = None
            if self.active is not None:
                self.active.cancel()
        for token in self.tokens:
            self.core.unsubscribe(token)
