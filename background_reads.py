"""Bounded background I/O; callers consume Futures on the UI owner."""
from concurrent.futures import Future
from queue import Empty, Full, Queue
from threading import Event, Thread, Lock
from time import monotonic
import math
import logging
from moonraker_client import MoonrakerError

_DEFAULT_QUEUE_TIMEOUT = object()

class ReadPending(Exception):
    pass


class ReadWorker:
    def __init__(self, timeout=5, capacity=32, queue_timeout=None):
        self.timeout = timeout
        self.queue_timeout = timeout if queue_timeout is None else queue_timeout
        self._queue = Queue(maxsize=capacity)
        self._stop = Event()
        self._lifecycle_lock = Lock()
        self._callbacks = []
        self._stopped = False
        self._thread = Thread(target=self._run, name='moonraker-reads', daemon=True)
        self._thread.start()

    def submit(self, work, queue_timeout=_DEFAULT_QUEUE_TIMEOUT):
        """Expire queued reads; explicit None preserves accepted local writes.

        Non-expiring work still uses the bounded queue and is cancelled by close.
        Network reads/commands must retain an admission deadline.
        """
        future = Future()
        wait = self.queue_timeout if queue_timeout is _DEFAULT_QUEUE_TIMEOUT else queue_timeout
        if wait is not None and (not math.isfinite(wait) or wait < 0):
            future.set_exception(MoonrakerError('Invalid read admission timeout'))
            return future
        with self._lifecycle_lock:
            if self._stop.is_set():
                future.set_exception(MoonrakerError('Read worker is closed'))
                return future
            try:
                deadline = None if wait is None else monotonic() + wait
                self._queue.put_nowait((future, work, deadline))
            except Full:
                future.set_exception(MoonrakerError('Read queue is full'))
        return future

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    future, work, deadline = self._queue.get(timeout=.1)
                except Empty:
                    continue
                try:
                    if not self._stop.is_set() and future.set_running_or_notify_cancel():
                        try:
                            if deadline is not None and monotonic() >= deadline:
                                raise MoonrakerError('Read expired before execution')
                            future.set_result(work())
                        except Exception as error:
                            future.set_exception(error)
                    elif not future.done():
                        future.cancel()
                finally:
                    self._queue.task_done()

        finally:
            with self._lifecycle_lock:
                self._stopped = True
                callbacks, self._callbacks = self._callbacks, []
            for callback in callbacks:
                try:
                    callback()
                except Exception:
                    logging.exception('Read resource finalizer failed')

    def on_stopped(self, callback):
        """Keep shared resources alive until started I/O has actually ended."""
        with self._lifecycle_lock:
            stopped = self._stopped
            if not stopped:
                self._callbacks.append(callback)
        if stopped:
            callback()

    def close(self):
        with self._lifecycle_lock:
            self._stop.set()
        while True:
            try:
                future, _, _ = self._queue.get_nowait()
            except Empty:
                break
            future.cancel()
            self._queue.task_done()
        self._thread.join(timeout=self.timeout + 1)
        return not self._thread.is_alive()
