"""Virtual Klipper buzzer transport, priority, and protocol tests."""
from pathlib import Path
from threading import Event
import socket
import struct
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from buzzer_ipc import BuzzerServer, PACKET, decode
from buzzer_control import Player, Settings
from klipper_extras.petrel_buzzer import PetrelBuzzer


class VirtualBuzzerTests(unittest.TestCase):
    def test_protocol_rejects_bad_frames_and_invalid_duty(self):
        self.assertEqual(decode(PACKET.pack(b'PB1', .75, .001)), (.75, .001))
        self.assertIsNone(decode(b'x' * PACKET.size))
        self.assertIsNone(decode(PACKET.pack(b'PB1', float('nan'), .001)))
        self.assertIsNone(decode(PACKET.pack(b'PB1', 1.2, .001)))
        self.assertIsNone(decode(PACKET.pack(b'PB1', .5, 0.)))
        self.assertIsNone(decode(PACKET.pack(b'PB1', .5, 1.2)))
        self.assertIsNone(decode(b''))

    def test_unix_ipc_listener_propagates_absolute_duty_without_pwm_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'klipper-buzzer.sock'
            player = Mock()
            done = Event()
            player.set_external.side_effect = lambda *args: done.set()
            with_server = BuzzerServer(path, player)
            try:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                    client.sendto(PACKET.pack(b'PB1', .5, .001), str(path))
                self.assertTrue(done.wait(1))
                player.set_external.assert_called_once_with(.5, .001)
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                    client.sendto(PACKET.pack(b'bad', .5, .001), str(path))
                time.sleep(.02)
                player.set_external.assert_called_once()
            finally:
                with_server.close()
            self.assertFalse(path.exists())

    def test_master_disabled_drops_ipc_and_mutes_existing_level(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'klipper-buzzer.sock'
            event = Event()
            player = Mock()
            player.mute_external.side_effect = event.set
            server = BuzzerServer(path, player, enabled=lambda: False)
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                    client.sendto(PACKET.pack(b'PB1', .8, .001), str(path))
                self.assertTrue(event.wait(1))
                player.set_external.assert_not_called()
                player.mute_external.assert_called_once()
            finally:
                server.close()

    def test_klipper_module_registers_existing_set_pin_and_preserves_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'klipper-buzzer.sock'
            player = Mock()
            arrived = Event()
            player.set_external.side_effect = lambda *args: arrived.set()
            server = BuzzerServer(path, player)
            try:
                printer = Mock()
                callbacks = []
                printer.lookup_object('toolhead').register_lookahead_callback.side_effect = callbacks.append
                config = Mock()
                config.get_printer.return_value = printer
                config.get_name.return_value = 'petrel_buzzer Buzzer'
                config.get.return_value = str(path)
                defaults = {'scale': 2., 'value': 0., 'shutdown_value': 0., 'cycle_time': .001}
                config.getfloat.side_effect = lambda name, default=None, **kwargs: defaults.get(name, default)
                obj = PetrelBuzzer(config)
                registered = printer.lookup_object('gcode').register_mux_command.call_args
                self.assertEqual(registered.args[:3], ('SET_PIN', 'PIN', 'Buzzer'))
                self.assertEqual(registered.args[3], obj.cmd_SET_PIN)
                gcmd = Mock()
                gcmd.get_float.side_effect = lambda name, default=None, **kwargs: {'VALUE': 1., 'CYCLE_TIME': .002}[name]
                obj.cmd_SET_PIN(gcmd)
                self.assertEqual(len(callbacks), 1)
                callbacks.pop()(0.)
                self.assertTrue(arrived.wait(1))
                player.set_external.assert_called_once_with(.5, .002)
                arrived.clear()
                obj._stop()
                self.assertTrue(arrived.wait(1))
                self.assertEqual(player.set_external.call_args.args, (0., .002))
            finally:
                server.close()

    def test_unavailable_server_does_not_fail_gcode(self):
        with tempfile.TemporaryDirectory() as folder:
            printer = Mock()
            config = Mock()
            config.get_printer.return_value = printer
            config.get_name.return_value = 'petrel_buzzer Buzzer'
            config.get.return_value = str(Path(folder) / 'missing.sock')
            config.getfloat.side_effect = lambda name, default=None, **kwargs: default
            buzzer = PetrelBuzzer(config)
            with self.assertLogs(level='WARNING'):
                self.assertFalse(buzzer._send(.5, .001))

    def test_emergency_preempts_and_blocks_external_gcode(self):
        pwm = Mock()
        started = Event()
        pwm.tone.side_effect = lambda *args: started.set()
        player = Player(driver_factory=lambda: pwm)
        try:
            self.assertTrue(player.set_external(.75, .001))
            deadline = time.monotonic() + 1
            while not pwm.set_pwm.called and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(pwm.set_pwm.called)
            self.assertTrue(player.play_emergency())
            self.assertTrue(started.wait(1))
            self.assertFalse(player.set_external(.3, .002))
            self.assertFalse(player.play(Settings(), 'press'))
            player.cancel()  # Cannot cancel an emergency alarm.
            deadline = time.monotonic() + 3.
            while (player.busy or player.emergency_pending) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertFalse(player.emergency_active)
            self.assertIsNone(player.external)
        finally:
            player.close()

    def test_external_safety_expiry(self):
        pwm = Mock()
        off = Event()
        pwm.off.side_effect = lambda: off.set()
        with patch.object(Player, 'EXTERNAL_MAX_SECONDS', .025):
            player = Player(driver_factory=lambda: pwm)
            try:
                self.assertTrue(player.set_external(1., .001))
                time.sleep(.075)
                self.assertIsNone(player.external)
                self.assertTrue(off.is_set())
            finally:
                player.close()


if __name__ == '__main__':
    unittest.main()
