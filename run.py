#!/usr/bin/env python3
import argparse
import logging
import math
import os
import signal


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--moonraker-url', default=os.environ.get('MOONRAKER_URL', 'http://127.0.0.1:7125'))
    parser.add_argument('--request-timeout', type=float, default=os.environ.get('PETREL_REQUEST_TIMEOUT', '5'))
    parser.add_argument('--serial-port', default=os.environ.get('PETREL_SERIAL_PORT', '/dev/ttyAMA0'))
    parser.add_argument('--encoder-pins', type=int, nargs=2, default=os.environ.get('PETREL_ENCODER_PINS', '21 16').split())
    parser.add_argument('--button-pin', type=int, default=os.environ.get('PETREL_BUTTON_PIN', '13'))
    parser.add_argument('--buzzer-gpio', type=int, default=os.environ.get('PETREL_BUZZER_GPIO', '19'),
                        help='BCM pin for native hardware PWM buzzer (12, 13, 18 or 19)')
    parser.add_argument('--settings-file', default=os.environ.get('PETREL_SETTINGS_FILE'), help='Local preset JSON path')
    parser.add_argument('--power-device', default=os.environ.get('PETREL_POWER_DEVICE', 'Printer'),
                        help='Moonraker power device controlled by the encoder button')
    parser.add_argument('--power-on-hold-ms', type=int,
                        default=os.environ.get('PETREL_POWER_ON_HOLD_MS', '2000'),
                        help='Encoder-button hold time for power-on in milliseconds; 0 powers on immediately')
    parser.add_argument('--emulator', action=argparse.BooleanOptionalAction,
                        default=os.environ.get('PETREL_EMULATOR', '0').lower() in ('1', 'true', 'yes', 'on'),
                        help='Enable the developer framebuffer mirror (default: off)')
    parser.add_argument('--emulator-socket', default=os.environ.get('PETREL_EMULATOR_SOCKET'))
    parser.add_argument('--emulator-font', default=os.environ.get('PETREL_EMULATOR_FONT'))
    parser.add_argument('--screenshot-directory', default=os.environ.get('PETREL_SCREENSHOT_DIRECTORY'))
    parser.add_argument('--remote', action=argparse.BooleanOptionalAction,
                        default=os.environ.get('PETREL_REMOTE', '0').lower() in ('1', 'true', 'yes', 'on'),
                        help='Enable the network LCD mirror and virtual encoder (default: off)')
    parser.add_argument('--remote-host', choices=('0.0.0.0', 'tailscale', '127.0.0.1'),
                        default=os.environ.get('PETREL_REMOTE_HOST', '0.0.0.0'),
                        help='Listen on all IPv4 interfaces (default), Tailscale only, or localhost')
    parser.add_argument('--remote-port', type=int,
                        default=os.environ.get('PETREL_REMOTE_PORT', '8088'),
                        help='Remote-display HTTP port (default: 8088)')
    return parser


def parse_args(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.encoder_pins = tuple(int(pin) for pin in args.encoder_pins)
        pins = args.encoder_pins + (args.button_pin,)
        if len(args.encoder_pins) != 2 or len(set(pins)) != 3 or any(pin < 0 or pin > 27 for pin in pins):
            raise ValueError('Use three distinct BCM pins in the range 0..27')
        if args.buzzer_gpio not in (12, 13, 18, 19):
            raise ValueError('Buzzer GPIO must support hardware PWM (12, 13, 18, 19)')
        if args.buzzer_gpio in pins:
            # Legacy installations may still have GPIO19 assigned to encoder B.
            # Do not prevent the entire display UI from launching on an update.
            os.environ['PETREL_BUZZER_DISABLED'] = '1'
            logging.warning('Buzzer GPIO conflicts with encoder/button; run configure.sh '
                            'and assign a free PWM pin before enabling sounds')
        else:
            os.environ.pop('PETREL_BUZZER_DISABLED', None)
        if not math.isfinite(args.request_timeout) or args.request_timeout <= 0:
            raise ValueError('Request timeout must be finite and positive')
        if not args.serial_port:
            raise ValueError('Serial port must not be empty')
        if not args.power_device.strip():
            raise ValueError('Power device must not be empty')
        if args.power_on_hold_ms < 0:
            raise ValueError('Power-on hold time must be zero or greater')
        if not 1 <= args.remote_port <= 65535:
            raise ValueError('Remote display port must be 1..65535')
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    return args


def main():
    logging.basicConfig(level=logging.INFO)
    if os.environ.get('PETREL_PROFILE_MEMORY_DIR'):
        from petrel.diagnostics.memory_profile import start_from_environment
        start_from_environment()
    from petrel.migration import bootstrap
    if bootstrap():
        return  # The independent migration job starts Petrel with its new paths.
    args = parse_args()
    # Keep explicit CLI overrides in sync with the hardware PWM worker.
    os.environ['PETREL_BUZZER_GPIO'] = str(args.buzzer_gpio)
    from petrel.application.display import PetrelDisplay
    display = PetrelDisplay(args.serial_port, tuple(args.encoder_pins), args.button_pin,
             os.environ.get('MOONRAKER_API_KEY', ''),
             moonraker_url=args.moonraker_url, request_timeout=args.request_timeout,
             settings_path=args.settings_file, power_device=args.power_device,
             power_on_hold_ms=args.power_on_hold_ms, emulator=args.emulator,
             emulator_socket=args.emulator_socket, screenshot_directory=args.screenshot_directory,
             emulator_font=args.emulator_font, remote=args.remote, remote_port=args.remote_port,
             remote_host=args.remote_host)
    signal.signal(signal.SIGTERM, lambda *_: display.lcdExit())
    server = None
    try:
        if os.environ.get('PETREL_KLIPPER_BUZZER', '0').lower() in ('1', 'true', 'yes', 'on'):
            from petrel.features.buzzer.control import Player
            from petrel.features.buzzer.ipc import BuzzerServer
            from pathlib import Path
            if getattr(display, '_buzzer_player', None) is None:
                display._buzzer_player = Player()
            path = Path.home() / '.config/Petrel/klipper-buzzer.sock'
            try:
                server = BuzzerServer(path, display._buzzer_player,
                                      enabled=display._buzzer_enabled)
            except OSError:
                logging.exception('Optional Klipper virtual buzzer socket unavailable')
        display.wait()
    finally:
        if server is not None:
            server.close()
        display.lcdExit()


if __name__ == '__main__':
    main()
