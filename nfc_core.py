"""Event-driven NFC Core: one backend, prioritized dispatch, bounded operations.

No libnfc import or direct printer/Spoolman/Happy Hare calls. Services register
short, nonblocking callbacks. UI handlers must post into the LCD owner's queue.
"""
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from threading import RLock

from nfc_settings import settings_path


CONSUMED = True
GLOBAL_PRIORITY = 1000
ALLOWED_GLOBAL_ACTIONS = frozenset(('emergency_stop',))


@dataclass(frozen=True)
class Subscription:
    token: int
    event: str
    callback: object
    priority: int
    scope: object


def normalize_uid(uid):
    if not isinstance(uid, str):
        raise ValueError('Invalid UID')
    value = uid.replace(':', '').replace(' ', '').upper()
    if len(value) < 4 or len(value) > 64 or len(value) % 2 or any(
            c not in '0123456789ABCDEF' for c in value):
        raise ValueError('Invalid UID')
    return ':'.join(value[i:i + 2] for i in range(0, len(value), 2))


class NFCCore:
    """No UI thread, loop, or second hardware owner is created."""

    def __init__(self, backend, *, emergency_stop=None, actions_file=None,
                 serial_devices=None):
        self.backend = backend
        self._serial_devices = serial_devices
        self._lock = RLock()
        self._subscribers = {}
        self._serial = 0
        self._scope = None
        self._current = None
        self._last = None
        self._identity = backend.identity()
        self._status = backend.snapshot()[1]
        self._capabilities = backend.capabilities()
        self._closed = False
        self._operations = deque(maxlen=8)
        self._emergency_stop = emergency_stop
        self._assignment = None
        self._actions_file = Path(actions_file or settings_path().with_name('nfc-actions.json'))
        self._global_actions = self._load_actions()
        self.subscribe('card.detected', self._dispatch_global, priority=GLOBAL_PRIORITY)
        self.subscribe('card.detected', self._capture_assignment, priority=100)
        backend.set_event_sink(self._on_backend_event)

    def _load_actions(self):
        try:
            raw = json.loads(self._actions_file.read_text('utf-8'))
            if not isinstance(raw, dict):
                return {}
            return {normalize_uid(uid): action for uid, action in raw.items()
                    if action in ALLOWED_GLOBAL_ACTIONS}
        except (OSError, ValueError, TypeError):
            return {}

    def global_action_uid(self, action):
        """Return the saved UID without exposing the mutable action mapping."""
        with self._lock:
            return next((uid for uid, name in self._global_actions.items()
                         if name == action), None)

    def begin_assignment(self):
        """Capture the NEXT arrival; saved emergency tags always preempt capture.

        No cached/last card is enrolled and nothing is persisted here. The LCD
        owner must explicitly confirm assign_global_action after capture.
        """
        with self._lock:
            if self._closed:
                raise OSError('NFC Core closed')
            if self._assignment is not None and not self._assignment.done():
                raise OSError('Tag assignment already active')
            self._assignment = Future()
            return self._assignment

    def _capture_assignment(self, card):
        with self._lock:
            future = self._assignment
            if future is None or future.done():
                return False
            try:
                uid = normalize_uid(card.get('uid'))
            except (TypeError, ValueError):
                return False
            # Lock cancellation and completion together via Future's own state.
            if not future.set_running_or_notify_cancel():
                return False
            future.set_result(dict(card, uid=uid))
        return CONSUMED

    def assign_global_action(self, action, uid):
        if action not in ALLOWED_GLOBAL_ACTIONS:
            raise ValueError('Unsupported global action')
        value = normalize_uid(uid)
        with self._lock:
            updated = {key: item for key, item in self._global_actions.items()
                       if key != value and item != action}
            updated[value] = action
            self._save_actions(updated)
            self._global_actions = updated

    def remove_global_action(self, action):
        if action not in ALLOWED_GLOBAL_ACTIONS:
            raise ValueError('Unsupported global action')
        with self._lock:
            updated = {uid: name for uid, name in self._global_actions.items()
                       if name != action}
            self._save_actions(updated)
            self._global_actions = updated

    def _save_actions(self, actions):
        import tempfile
        path = self._actions_file
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp = tempfile.mkstemp(prefix='.nfc-actions-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(actions, out, sort_keys=True)
                out.write('\n')
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temp, 0o600)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def _dispatch_global(self, card):
        try:
            uid = normalize_uid(card.get('uid'))
        except (TypeError, ValueError):
            return False
        with self._lock:
            action = self._global_actions.get(uid)
        if action != 'emergency_stop':
            return False
        # Never block the scanner waiting for the Moonraker WebSocket response.
        if self._emergency_stop is not None:
            try:
                future = self._emergency_stop()
                if isinstance(future, Future):
                    future.add_done_callback(self._emergency_result)
            except Exception:
                logging.exception('NFC emergency-stop dispatch failed')
        self._dispatch('action.emergency_stop', {'uid': uid})
        return CONSUMED

    @staticmethod
    def _emergency_result(future):
        try:
            future.result()
        except Exception:
            logging.exception('NFC emergency-stop request failed')

    def set_context(self, scope):
        with self._lock:
            self._scope = scope

    def subscribe(self, event, callback, priority=0, scope=None):
        if not callable(callback) or not isinstance(event, str) or not event:
            raise ValueError('Invalid NFC subscription')
        with self._lock:
            self._serial += 1
            item = Subscription(self._serial, event, callback, int(priority), scope)
            self._subscribers[item.token] = item
        return item.token

    def unsubscribe(self, token):
        with self._lock:
            return self._subscribers.pop(token, None) is not None

    def _dispatch(self, event, data):
        with self._lock:
            scope = self._scope
            callbacks = sorted((s for s in self._subscribers.values()
                                if s.event == event and (s.scope is None or s.scope == scope)),
                               key=lambda s: (-s.priority, s.token))
        for item in callbacks:
            try:
                if item.callback(dict(data)) is CONSUMED:
                    break
            except Exception:
                logging.exception('NFC event subscriber failed: %s', event)

    def _on_backend_event(self, event, data):
        with self._lock:
            if self._closed:
                return
            if event == 'card.detected':
                self._current = dict(data)
                self._last = dict(data)
            elif event == 'card.removed':
                self._current = None
            elif event == 'reader.changed':
                self._status = data.get('status', self._status)
                self._identity = dict(data.get('identity') or {})
                if self._status not in ('Listening', 'Partial support'):
                    self._current = None
            elif event == 'capabilities.changed':
                self._capabilities = dict(data)
        self._dispatch(event, data)

    def get_capabilities(self):
        with self._lock:
            return dict(self._capabilities)

    def get_status(self):
        with self._lock:
            return self._status

    def get_reader_info(self):
        with self._lock:
            return dict(self._identity)

    def is_ready(self):
        return self.get_status() in ('Listening', 'Partial support')

    def get_current_card(self):
        with self._lock:
            return dict(self._current) if self._current is not None else None

    def get_last_card(self):
        with self._lock:
            return dict(self._last) if self._last is not None else None

    def discover_devices(self, model, interface):
        # Serial devices use the existing Moonraker read worker; libnfc
        # enumeration remains on the backend's sole hardware worker.
        from nfc_settings import PROFILES
        if model not in PROFILES or interface not in PROFILES[model]['interfaces']:
            raise ValueError('Unsupported NFC reader/transport')
        if interface == 'UART' and self._serial_devices is not None:
            return self._serial_devices()
        return self.backend.discover_devices(model, interface)

    def test_connection(self, settings):
        return self.backend.test_connection(settings)

    def reload_configuration(self):
        return self.backend.reload_configuration()

    def share_ndef_uri(self, url):
        return self.submit('share_ndef_uri', url=url)

    def cancel_share(self):
        return self.backend.cancel_share()

    def submit(self, operation, **kwargs):
        if operation != 'share_ndef_uri':
            raise NotImplementedError('NFC operation is not implemented by this backend')
        future = self.backend.share_ndef_uri(kwargs['url'])
        with self._lock:
            self._operations.append(future)
        future.add_done_callback(self._operation_done)
        return future

    def _operation_done(self, future):
        try:
            result = future.result()
        except Exception as error:
            self._dispatch('operation.failed', {'error': str(error)})
        else:
            self._dispatch('operation.completed', {'result': result})

    def close(self):
        with self._lock:
            self._closed = True
            if self._assignment is not None:
                self._assignment.cancel()
            self._subscribers.clear()
        self.backend.set_event_sink(None)
