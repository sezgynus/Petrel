"""Single libnfc subprocess owner; publish only the most recent card."""
import os
import re
import shutil
import subprocess
from threading import Event, Lock, Thread

from nfc_info import DEFAULT_DEVICE


def parse_card_line(line, previous):
    card = dict(previous)
    if 'target:' in line:
        match = re.search(r'^(.*?)\s*\((.*?)\) target:', line.strip())
        if match:
            card = {'type': match[1].replace('ISO/IEC ', 'ISO'), 'rate': match[2]}
    if 'UID (NFCID1):' in line:
        uid = line.split('UID (NFCID1):', 1)[1].split()
        if len(uid) in (4, 7, 10) and all(re.fullmatch('[0-9a-fA-F]{2}', b) for b in uid):
            card['uid'] = ':'.join(uid).upper()
    for marker, key in (('ATQA (SENS_RES):', 'atqa'), ('SAK (SEL_RES):', 'sak')):
        if marker in line:
            value = line.split(marker, 1)[1].strip()
            if re.fullmatch(r'[0-9a-fA-F ]+', value):
                card[key] = ' '.join(value.upper().split())
    return card


class RFIDReader:
    def __init__(self):
        self._stop = Event()
        self._lock = Lock()
        self._process = None
        self._card = {}
        self._status = 'Starting...'
        self._revision = 0
        self._thread = Thread(target=self._run, name='petrel-rfid', daemon=True)
        self._thread.start()

    def snapshot(self):
        with self._lock:
            return self._revision, self._status, dict(self._card)

    def _publish(self, status, card=None):
        with self._lock:
            latest = card if card and card.get('uid') else self._card
            if status != self._status or latest != self._card:
                self._status, self._card = status, dict(latest)
                self._revision += 1

    def _run(self):
        tool, stdbuf = shutil.which('nfc-poll'), shutil.which('stdbuf')
        if not tool or not stdbuf:
            self._publish('nfc-poll missing')
            return
        env = dict(os.environ, LC_ALL='C', LIBNFC_LOG_LEVEL='0',
                   LIBNFC_DEVICE=os.environ.get('PETREL_NFC_DEVICE', DEFAULT_DEVICE),
                   LIBNFC_AUTO_SCAN='false', LIBNFC_INTRUSIVE_SCAN='false')
        while not self._stop.is_set():
            process = None
            try:
                with self._lock:
                    if self._stop.is_set():
                        break
                    process = subprocess.Popen([stdbuf, '-oL', tool, '-v'], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        text=True, errors='replace')
                    self._process = process
                self._publish('Listening')
                current = {}
                for line in process.stdout:
                    if self._stop.is_set():
                        break
                    current = parse_card_line(line, current)
                    if current.get('uid'):
                        self._publish('Listening', current)
                code = process.wait()
                if code and not self._stop.is_set():
                    self._publish('Reader unavailable')
                    self._stop.wait(2)
            except OSError:
                self._publish('Reader unavailable')
                self._stop.wait(2)
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    process.stdout.close()
                with self._lock:
                    self._process = None

    def close(self):
        self._stop.set()
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None:
                process.terminate()
        self._thread.join(timeout=2)
