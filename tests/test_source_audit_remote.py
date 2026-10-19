"""CI-only remote limits and unchanged/animated frame cache contracts."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import BoundedSemaphore
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import socket
import time
import unittest
from urllib.request import urlopen
from PIL import Image
from dwin_emulator.remote import RemoteDisplayServer, _HTTP, PAGE
from dwin_emulator.runtime import Emulator
from dwin_emulator.framebuffer import Framebuffer

class AuditRemoteTests(unittest.TestCase):
    def test_one_jpeg_is_shared_and_disconnection_does_not_serve_stale_frame(self):
        model=Mock();model.errors=set();model.presented=Image.new('RGB',(272,480),'red')
        model.frame_token.return_value=(1,())
        model.snapshot.return_value=(model.presented,1)
        emulator=Emulator(enabled=True,factory=lambda:model);emulator.baseline=emulator.online=True
        server=RemoteDisplayServer(emulator,lambda *a:True,port=0,host='127.0.0.1')
        self.addCleanup(server.close)
        with ThreadPoolExecutor(max_workers=4) as pool:
            frames=list(pool.map(lambda _:server.frame_bytes(),range(4)))
        self.assertTrue(all(frame is frames[0] for frame in frames))
        model.snapshot.assert_called_once()
        model.frame_token.return_value=(1,((0,1),))
        server.frame_bytes();self.assertEqual(model.snapshot.call_count,2)
        emulator.disconnect_panel()
        with self.assertRaises(RuntimeError):server.frame_bytes()
        self.assertIsNone(server._jpeg)

    def test_animation_token_changes_without_new_uart_presentation(self):
        f=Framebuffer.__new__(Framebuffer)
        from threading import RLock
        f.lock=RLock();f.sequence=12
        f.animations={0:(0,0,0x80,3,1,3,10,0,None)}
        with patch('dwin_emulator.framebuffer.time.monotonic',return_value=.01):a=f.frame_token()
        with patch('dwin_emulator.framebuffer.time.monotonic',return_value=.11):b=f.frame_token()
        self.assertNotEqual(a,b);self.assertEqual(a[0],b[0])

    def test_connection_capacity_rejects_before_starting_another_thread(self):
        server=_HTTP.__new__(_HTTP);server._slots=BoundedSemaphore(1)
        server.shutdown_request=Mock();server._slots.acquire()
        with patch('http.server.ThreadingHTTPServer.process_request') as dispatch:
            server.process_request(Mock(),('127.0.0.1',1))
            dispatch.assert_not_called();server.shutdown_request.assert_called_once()

    def test_partial_input_body_expires_and_never_enqueues(self):
        enqueue=Mock()
        with patch.object(_HTTP,'READ_TIMEOUT',.15):
            server=RemoteDisplayServer(Mock(),enqueue,port=0,host='127.0.0.1')
            self.addCleanup(server.close)
            with socket.create_connection(('127.0.0.1',server.port),timeout=1) as connection:
                connection.settimeout(1)
                connection.sendall(('POST /input HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\nX-Petrel-Remote: 1\r\nContent-Length: 16\r\n\r\n{'%server.port).encode())
                reply=connection.recv(1024)
                self.assertIn(b'408',reply)
            enqueue.assert_not_called()

    def test_keyboard_enter_is_scoped_and_repeat_safe(self):
        self.assertIn('view.addEventListener("keydown"',PAGE)
        self.assertIn('event.key !== "Enter" || event.repeat',PAGE)
        self.assertIn('event.target.closest("button, input, textarea, select, [contenteditable]")',PAGE)
