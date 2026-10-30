"""Bounded local IPC receiver for the optional Klipper virtual buzzer.

AF_UNIX datagrams let Klipper deliver SET_PIN without waiting for Petrel.
Only the PWM worker writes hardware registers. The socket is private to
Petrel's service account and is removed only when owned by this instance.
"""
import logging
import math
import os
from pathlib import Path
import socket
import stat
import struct
import threading

MAGIC = b'PB1'
PACKET = struct.Struct('!3sdd')


def decode(payload):
    if len(payload) != PACKET.size:
        return None
    magic, value, cycle = PACKET.unpack(payload)
    if (magic != MAGIC or not math.isfinite(value) or not 0 <= value <= 1
            or not math.isfinite(cycle) or not .00005 <= cycle <= 1):
        return None
    return value, cycle


class BuzzerServer:
    def __init__(self, path, player, enabled=None):
        self.path = Path(path)
        self.player = player
        self.enabled = enabled if enabled is not None else lambda: True
        self.stopping = threading.Event()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.stat().st_uid != os.getuid():
            raise OSError('Buzzer socket parent not owned by Petrel user')
        if os.path.lexists(self.path):
            old = self.path.lstat()
            if not stat.S_ISSOCK(old.st_mode) or old.st_uid != os.getuid():
                raise OSError('Refusing to remove foreign buzzer IPC path')
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                probe.connect(str(self.path))
            except OSError:
                self.path.unlink()  # Stale socket owned by this user.
            else:
                raise OSError('Another Petrel buzzer server is running')
            finally:
                probe.close()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.sock.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self.inode = self.path.lstat().st_ino
            self.sock.settimeout(.1)
        except BaseException:
            self.sock.close()
            raise
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name='petrel-klipper-buzzer')
        self.thread.start()

    def _run(self):
        while not self.stopping.is_set():
            try:
                payload = self.sock.recv(128)
            except socket.timeout:
                continue
            except OSError:
                if not self.stopping.is_set():
                    logging.exception('Klipper buzzer IPC receive failed')
                break
            event = decode(payload)
            if event is not None:
                try:
                    if self.enabled():
                        self.player.set_external(*event)
                    else:
                        self.player.mute_external()
                except Exception:
                    logging.exception('Virtual buzzer IPC dispatch failed')

    def close(self):
        self.stopping.set()
        self.sock.close()
        self.thread.join(timeout=1)
        try:
            if self.path.lstat().st_ino == self.inode:
                self.path.unlink()
        except FileNotFoundError:
            pass
