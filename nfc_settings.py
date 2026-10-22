"""Runtime NFC reader choices and persistent configuration."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile


# libnfc upstream drivers. Keep model/interface choices tied to driver families;
# individual commercial boards are not all separately named by libnfc.
PROFILES = {
    'PN532': {'interfaces': ('UART', 'I2C', 'SPI'),
              'drivers': {'UART': 'pn532_uart', 'I2C': 'pn532_i2c', 'SPI': 'pn532_spi'}},
    'PN53x USB': {'interfaces': ('USB',), 'drivers': {'USB': 'pn53x_usb'}},
    'ACR122U': {'interfaces': ('USB', 'PC/SC'),
                'drivers': {'USB': 'acr122_usb', 'PC/SC': 'acr122_pcsc'}},
    'ACR122S': {'interfaces': ('UART',), 'drivers': {'UART': 'acr122s'}},
    'ARYGON': {'interfaces': ('UART',), 'drivers': {'UART': 'arygon'}},
    'PC/SC reader': {'interfaces': ('PC/SC',), 'drivers': {'PC/SC': 'pcsc'}},
    'PN71xx': {'interfaces': ('NCI',), 'drivers': {'NCI': 'pn71xx'}},
}

BAUD_RATES = (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600)


def settings_path():
    root = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return root / 'Petrel' / 'nfc-settings.json'


@dataclass(frozen=True)
class NFCSettings:
    model: str = 'PN532'
    interface: str = 'UART'
    port: str = ''
    speed: int = 115200

    def validate(self):
        profile = PROFILES.get(self.model)
        if profile is None or self.interface not in profile['interfaces']:
            raise ValueError('Unsupported NFC model/interface')
        if not self.port:
            raise ValueError('An NFC port/device must be selected')
        if self.interface == 'UART' and self.speed not in BAUD_RATES:
            raise ValueError('Unsupported NFC interface speed')
        if self.interface != 'UART' and self.speed != 0:
            raise ValueError('This NFC interface has no configurable speed')
        return self

    def connection_string(self):
        self.validate()
        driver = PROFILES[self.model]['drivers'][self.interface]
        if self.interface == 'UART':
            return f'{driver}:{self.port}:{self.speed}'
        if self.interface == 'I2C':
            return f'pn532_i2c:{self.port}'
        if self.interface == 'SPI':
            return f'pn532_spi:{self.port}'
        if self.interface in ('USB', 'PC/SC', 'NCI'):
            return self.port
        return f'{driver}:{self.port}'


def load(path=None):
    path = Path(path or settings_path())
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        result = NFCSettings(**raw)
        return result.validate()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return NFCSettings()


def save(settings, path=None):
    settings.validate()
    target = Path(path or settings_path())
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.nfc-settings-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(asdict(settings), stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def installed_enabled(environ=None):
    value = (environ or os.environ).get('PETREL_NFC', '0')
    return str(value).strip().lower() in ('1', 'y', 'yes', 'true', 'on')


def serial_ports_from_moonraker(response):
    """One canonical path per UART, matching Moonraker's serial device list.

    Never treat by-id/by-path links or /dev/serial* aliases as extra ports.
    Invalid or unexpected responses fail closed rather than triggering a local
    /dev scan that would resurrect the duplicate entries.
    """
    if not isinstance(response, dict) or not isinstance(response.get('result'), dict):
        raise ValueError('Invalid Moonraker serial response')
    entries = response['result'].get('serial_devices')
    if not isinstance(entries, list):
        raise ValueError('Moonraker serial_devices must be a list')
    paths, seen = [], set()
    for device in entries:
        if not isinstance(device, dict):
            continue
        if device.get('device_type') not in ('hardware_uart', 'usb'):
            continue
        path = device.get('device_path')
        if (not isinstance(path, str) or not path.startswith('/dev/')
                or not path[5:] or '/' in path[5:] or path in seen):
            continue
        seen.add(path)
        paths.append(path)
    return tuple(paths)


def available_ports(interface, profile, dev='/dev'):
    """Discover non-UART interfaces; UART is supplied only by Moonraker."""
    root = Path(dev)
    if interface == 'UART':
        # The NFC menu uses serial_ports_from_moonraker via its read worker.
        # Do not silently fall back to the old duplicate-prone glob scan.
        return ()
    if interface == 'I2C':
        paths = list(root.glob('i2c-*'))
    elif interface == 'SPI':
        paths = list(root.glob('spidev*'))
    elif interface in ('USB', 'PC/SC', 'NCI'):
        # Pure settings helper: only NFCBackend may call libnfc enumeration.
        # Never open a competing libnfc context from a settings/UI caller.
        paths = []
    else:
        paths = []
    result = []
    for path in paths:
        try:
            if path.exists() and path not in result:
                result.append(path)
        except OSError:
            continue
    return tuple(str(path) for path in result)
