"""One owner for initialization, UI events, periodic rendering and shutdown."""
from dataclasses import dataclass
import logging
import math
from queue import Empty, Full, Queue
from threading import Event, Thread, current_thread
import time


@dataclass(frozen=True)
class InputEvent:
    kind: str
    value: int
    epoch: int
    ui_epoch: int = 0
    accelerated_value: int = 0
    rate: float = 0.0


class UIEventLoop:
    def __init__(self, initialize, handle_event, tick, cleanup,
                 interval=2.0, capacity=256):
        if not math.isfinite(interval) or interval <= 0 or capacity < 1:
            raise ValueError('UI interval and queue capacity must be positive')
        self._initialize = initialize
        self._handle_event = handle_event
        self._tick = tick
        self._cleanup = cleanup
        self._interval = interval
        self._queue = Queue(maxsize=capacity)
        self._coalesced = {}  # At most 32 distinct completion kinds, independent of input backlog.
        self._stop = Event()
        self._ready = Event()
        self._done = Event()
        self._startup_error = None
        self._thread = Thread(target=self._run, name='lcd-ui', daemon=True)

    def start(self):
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            self._done.wait()
            raise self._startup_error

    def post(self, event):
        if self._stop.is_set():
            return False
        # Collapse adjacent same-direction encoder events while the UI owner is
        # busy. Raw steps are preserved for menus; accelerated steps are
        # preserved separately for numeric editors.
        if isinstance(event, InputEvent) and event.kind == 'rotate':
            with self._queue.mutex:
                if self._queue.queue:
                    previous = self._queue.queue[-1]
                    if (isinstance(previous, InputEvent) and previous.kind == 'rotate'
                            and previous.epoch == event.epoch
                            and previous.ui_epoch == event.ui_epoch
                            and (previous.value > 0) == (event.value > 0)):
                        self._queue.queue[-1] = InputEvent(
                            'rotate', previous.value + event.value, event.epoch, event.ui_epoch,
                            previous.accelerated_value + event.accelerated_value, event.rate)
                        return True
        try:
            self._queue.put_nowait(event)
        except Full:
            return False
        return True

    def post_coalesced(self, event):
        """Retain latest state notifications even when the input queue is full.

        Payload owners retain Futures/results. Repeated wakeups of one kind need
        only one owner callback; never drop encoder/press events to make room.
        """
        key = event.kind
        if not isinstance(key, str) or not key:
            raise ValueError('Completion kind must be a nonempty string')
        with self._queue.mutex:
            if self._stop.is_set():
                return False
            fresh = key not in self._coalesced
            if fresh and len(self._coalesced) >= 32:
                return False
            self._coalesced[key] = event
        if fresh:
            try:
                self._queue.put_nowait(None)  # Wake a sleeping owner if space exists.
            except Full:
                pass  # A full input queue already keeps the owner awake.
        return True

    def _drain_coalesced(self):
        with self._queue.mutex:
            events = tuple(self._coalesced.values())
            self._coalesced.clear()
        for event in events:
            if self._stop.is_set():
                break
            self._invoke(self._handle_event, event)

    def set_interval(self, interval):
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError('UI interval must be positive')
        self._interval = interval

    def cap_interval(self, maximum):
        """Apply an operation deadline without slowing a faster render task."""
        self.set_interval(min(self._interval, maximum))

    def _run(self):
        try:
            try:
                self._initialize()
            except Exception as exc:
                self._startup_error = exc
                self._stop.set()
            finally:
                self._ready.set()
            next_tick = time.monotonic() + self._interval
            scheduled_interval = self._interval
            while not self._stop.is_set():
                self._drain_coalesced()
                if self._interval != scheduled_interval:
                    next_tick = min(next_tick, time.monotonic() + self._interval)
                    scheduled_interval = self._interval
                if time.monotonic() >= next_tick:
                    self._invoke(self._tick)
                    # No catch-up burst after slow rendering.
                    next_tick = time.monotonic() + self._interval
                    scheduled_interval = self._interval
                try:
                    event = self._queue.get(timeout=max(0, next_tick - time.monotonic()))
                except Empty:
                    continue
                if not self._stop.is_set() and event is not None:
                    self._invoke(self._handle_event, event)
                self._queue.task_done()
        finally:
            try:
                self._cleanup()
            except Exception:
                logging.exception('LCD cleanup failed')
            self._done.set()

    @staticmethod
    def _invoke(callback, *args):
        try:
            callback(*args)
        except Exception:
            logging.exception('LCD UI event failed')

    def close(self):
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        if self._thread.is_alive() and current_thread() is not self._thread:
            # Cleanup is owned by the UI thread, after any active render ends.
            self._thread.join()

    def wait(self):
        self._done.wait()
