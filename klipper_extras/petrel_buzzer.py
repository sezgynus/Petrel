"""Optional Petrel virtual PWM buzzer (no MCU output pin).

Accepts the SET_PIN PIN=Buzzer VALUE=... CYCLE_TIME=... grammar from
[pwm_cycle_time Buzzer], and delivers absolute duty over local Unix datagrams.
Never blocks a G-code/motion callback waiting for Petrel's UI.
"""
import logging
import socket
import struct
import time

PACKET = struct.Struct('!3sdd')
MAGIC = b'PB1'


class PetrelBuzzer:
    cmd_SET_PIN_help = 'Drive the Petrel virtual hardware-PWM buzzer'

    def __init__(self, config):
        self.printer = config.get_printer()
        self.pin_name = config.get_name().split(' ', 1)[1].strip()
        self.socket_path = config.get('socket_path')
        if not self.socket_path.startswith('/') or '\x00' in self.socket_path:
            raise config.error('petrel_buzzer socket_path must be absolute')
        self.scale = config.getfloat('scale', 1., above=0.)
        self.last_value = config.getfloat(
            'value', 0., minval=0., maxval=self.scale) / self.scale
        self.shutdown_value = config.getfloat(
            'shutdown_value', 0., minval=0., maxval=self.scale) / self.scale
        self.default_cycle_time = config.getfloat(
            'cycle_time', .001, minval=.00005, maxval=1.)
        self.last_cycle_time = self.default_cycle_time
        self.printer.lookup_object('gcode').register_mux_command(
            'SET_PIN', 'PIN', self.pin_name, self.cmd_SET_PIN,
            desc=self.cmd_SET_PIN_help)
        self.printer.register_event_handler('klippy:shutdown', self._stop)
        self.printer.register_event_handler('klippy:disconnect', self._stop)
        self._next_warning = 0.

    def _send(self, value, cycle_time):
        packet = PACKET.pack(MAGIC, value, cycle_time)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.setblocking(False)
                sock.sendto(packet, self.socket_path)
            return True
        except OSError as error:
            now = time.monotonic()
            if now >= self._next_warning:
                logging.warning('Petrel buzzer IPC unavailable: %s', error)
                self._next_warning = now + 60.
            return False

    def _stop(self):
        # Always send zero on orderly Klipper shutdown/disconnect.
        self._send(self.shutdown_value, self.last_cycle_time)

    def _set_pin(self, print_time, value, cycle_time):
        if value == self.last_value and cycle_time == self.last_cycle_time:
            return
        if self._send(value, cycle_time):
            self.last_value = value
            self.last_cycle_time = cycle_time

    def cmd_SET_PIN(self, gcmd):
        value = gcmd.get_float('VALUE', minval=0., maxval=self.scale)
        value /= self.scale
        cycle_time = gcmd.get_float(
            'CYCLE_TIME', self.default_cycle_time, minval=.00005, maxval=1.)
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.register_lookahead_callback(
            lambda print_time: self._set_pin(print_time, value, cycle_time))


def load_config_prefix(config):
    return PetrelBuzzer(config)
