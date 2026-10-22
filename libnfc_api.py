"""Direct public libnfc ABI. Packed layouts mirror nfc/nfc-types.h (1.8)."""
import ctypes as C
import ctypes.util
from functools import lru_cache

from nfc_info import parse_info

U8, SIZE, INT = C.c_uint8, C.c_size_t, C.c_int
PTR = C.c_void_p


def packed(name, fields):
    return type(name, (C.Structure,), {'_pack_': 1, '_fields_': fields})


ISOA = packed('ISOA', [('atqa', U8*2), ('sak', U8), ('uid_len', SIZE),
    ('uid', U8*10), ('ats_len', SIZE), ('ats', U8*254)])
Felica = packed('Felica', [('length', SIZE), ('code', U8), ('uid', U8*8),
    ('pad', U8*8), ('syscode', U8*2)])
ISOB = packed('ISOB', [('uid', U8*4), ('app', U8*4), ('protocol', U8*3), ('cid', U8)])
ISOBI = packed('ISOBI', [('uid', U8*4), ('version', U8), ('config', U8),
    ('atr_len', SIZE), ('atr', U8*33)])
UID8 = packed('UID8', [('uid', U8*8)])
ISOBCT = packed('ISOBCT', [('uid', U8*4), ('product', U8), ('factory', U8)])
Jewel = packed('Jewel', [('sens', U8*2), ('uid', U8*4)])
DEP = packed('DEP', [('uid', U8*10), ('did', U8), ('bs', U8), ('br', U8),
    ('timeout', U8), ('pp', U8), ('gb', U8*48), ('gb_len', SIZE), ('mode', INT)])
Barcode = packed('Barcode', [('length', SIZE), ('data', U8*32)])


class TargetInfo(C.Union):
    _pack_ = 1
    _fields_ = [('a', ISOA), ('felica', Felica), ('b', ISOB), ('bi', ISOBI),
                ('sr', UID8), ('ct', ISOBCT), ('jewel', Jewel), ('dep', DEP),
                ('barcode', Barcode), ('iclass', UID8)]


Modulation = packed('Modulation', [('kind', INT), ('baud', INT)])
Target = packed('Target', [('info', TargetInfo), ('modulation', Modulation)])
NAMES = {1: 'ISO14443A', 2: 'Jewel/Topaz', 3: 'ISO14443B', 4: "ISO14443B'",
         5: 'ST SRx', 6: 'ASK CTx', 7: 'FeliCa', 8: 'NFC-DEP',
         9: 'NFC Barcode', 10: 'iClass/PicoPass'}


def decode_target(target):
    kind, data = target.modulation.kind, target.info
    card = {'type': NAMES.get(kind, 'Unknown')}
    if kind == 1:
        if not 1 <= data.a.uid_len <= 10:
            raise ValueError('Invalid ISO14443A UID length')
        uid = bytes(data.a.uid[:data.a.uid_len])
        card.update(atqa=bytes(data.a.atqa).hex(' ').upper(), sak=f'{data.a.sak:02X}')
    elif kind == 9:
        if not 1 <= data.barcode.length <= 32:
            raise ValueError('Invalid NFC Barcode length')
        uid = bytes(data.barcode.data[:data.barcode.length])
    else:
        field = {2: 'jewel', 3: 'b', 4: 'bi', 5: 'sr', 6: 'ct',
                 7: 'felica', 8: 'dep', 10: 'iclass'}.get(kind)
        if field is None:
            raise ValueError('Unknown libnfc target type')
        uid = bytes(getattr(data, field).uid)
    card['uid'] = uid.hex(':').upper()
    card['rate'] = {1: '106 kbps', 2: '212 kbps', 3: '424 kbps', 4: '847 kbps'}.get(
        target.modulation.baud, 'Unknown')
    return card


@lru_cache(maxsize=1)
def bind_library():
    """Resolve and bind the libnfc ABI once per Petrel process.

    Context and device handles are still owned and closed per worker session.
    Only the immutable CDLL binding is shared to avoid repeated linker lookups.
    """
    path = C.util.find_library('nfc')
    if not path:
        raise OSError('libnfc missing')
    lib = C.CDLL(path)
    signatures = {
        'nfc_init': (None, [C.POINTER(PTR)]), 'nfc_exit': (None, [PTR]),
        'nfc_open': (PTR, [PTR, C.c_char_p]), 'nfc_close': (None, [PTR]),
        'nfc_abort_command': (INT, [PTR]), 'nfc_initiator_init': (INT, [PTR]),
        'nfc_version': (C.c_char_p, []),
        'nfc_strerror': (C.c_char_p, [PTR]),
        'nfc_device_get_information_about': (INT, [PTR, C.POINTER(PTR)]),
        'nfc_free': (None, [PTR]),
        'nfc_device_get_supported_modulation': (INT, [PTR, INT, C.POINTER(C.POINTER(INT))]),
        'nfc_device_get_supported_baud_rate': (INT, [PTR, INT, C.POINTER(C.POINTER(INT))]),
        'nfc_device_set_property_bool': (INT, [PTR, INT, C.c_bool]),
        'nfc_device_set_property_int': (INT, [PTR, INT, INT]),
        'nfc_initiator_select_passive_target': (INT, [PTR, Modulation, PTR, SIZE, C.POINTER(Target)]),
        'nfc_initiator_select_dep_target': (INT, [PTR, INT, INT, PTR, C.POINTER(Target), INT]),
        'nfc_initiator_deselect_target': (INT, [PTR]),
        'nfc_target_init': (INT, [PTR, C.POINTER(Target), PTR, SIZE, INT]),
        'nfc_target_send_bytes': (INT, [PTR, PTR, SIZE, INT]),
        'nfc_target_receive_bytes': (INT, [PTR, PTR, SIZE, INT]),
        'nfc_device_get_supported_baud_rate_target_mode':
            (INT, [PTR, INT, C.POINTER(C.POINTER(INT))]),
    }
    for name, (result, args) in signatures.items():
        function = getattr(lib, name)
        function.restype, function.argtypes = result, args
    return lib


def list_devices(limit=32):
    """Ask the installed libnfc build to enumerate its compatible devices."""
    if not 1 <= int(limit) <= 256:
        raise ValueError('Invalid NFC device limit')
    lib = bind_library()
    connstring = C.c_char * 1024
    devices = (connstring * int(limit))()
    context = PTR()
    lib.nfc_init.argtypes = [C.POINTER(PTR)]
    lib.nfc_init(C.byref(context))
    if not context:
        raise OSError('libnfc context unavailable')
    try:
        enumerate_devices = lib.nfc_list_devices
        enumerate_devices.restype = SIZE
        enumerate_devices.argtypes = [PTR, C.POINTER(connstring), SIZE]
        count = min(int(enumerate_devices(context, devices, int(limit))), int(limit))
        return tuple(bytes(devices[index]).split(b'\0', 1)[0].decode('utf-8', 'replace')
                     for index in range(count))
    finally:
        lib.nfc_exit(context)


def check_connection(settings):
    """Verify a selected reader with libnfc without requiring a card.

    Deliberately bypasses PETREL_NFC_DEVICE and the saved settings: the menu
    tests its *current draft*. The caller must serialize this operation with
    any active RFIDSession, since most NFC devices are exclusive-access.
    """
    connection = settings.connection_string()
    lib = bind_library()
    context = PTR()
    device = None
    try:
        lib.nfc_init(C.byref(context))
        if not context:
            raise OSError('libnfc context unavailable')
        device = lib.nfc_open(context, connection.encode('utf-8'))
        if not device:
            raise OSError('Unable to open NFC reader')
        result = lib.nfc_initiator_init(device)
        if result < 0:
            raise OSError('Cannot initialize NFC reader (libnfc error %d)' % result)
        return True
    finally:
        if device:
            lib.nfc_close(device)
        if context:
            lib.nfc_exit(context)


class NFCSession:
    """One libnfc initiator handle bound to an explicit, validated device.

    The backend owns this session. No environment defaults, discovery, or
    configuration-file I/O are permitted inside the driver session.
    """
    def __init__(self, settings):
        connection = settings.connection_string()
        self.lib = bind_library()
        self.context, self.device = PTR(), None
        try:
            self.lib.nfc_init(C.byref(self.context))
            if not self.context:
                raise OSError('libnfc context unavailable')
            self.device = self.lib.nfc_open(self.context, connection.encode('utf-8'))
            if not self.device:
                raise OSError('NFC reader unavailable')
            self._check(self.lib.nfc_initiator_init(self.device))
            # NP_INFINITE_SELECT=False: one RF activation attempt per turn.
            # No 150/300 ms AutoPoll delay and no wait-for-removal loop.
            self._check(self.lib.nfc_device_set_property_bool(self.device, 7, False))
            self._check(self.lib.nfc_device_set_property_int(self.device, 0, 1000))
            self.modulations = self._modulations()
            if not self.modulations:
                raise OSError('No supported NFC card technologies')
        except BaseException:
            self.close()
            raise

    def _check(self, result, operation='initialization'):
        if result < 0:
            detail = self.lib.nfc_strerror(self.device)
            if isinstance(detail, bytes):
                detail = detail.decode('utf-8', 'replace')
            raise OSError(f'{operation}: libnfc error {result} ({detail})')
        return result

    def _modulations(self):
        kinds = C.POINTER(INT)()
        self._check(self.lib.nfc_device_get_supported_modulation(self.device, 1, C.byref(kinds)))
        result = []
        for index in range(16):
            kind = kinds[index]
            if not kind:
                break
            rates = C.POINTER(INT)()
            self._check(self.lib.nfc_device_get_supported_baud_rate(self.device, kind, C.byref(rates)))
            for offset in range(8):
                rate = rates[offset]
                if not rate:
                    break
                # Type A activation starts at 106; higher rates are negotiated
                # after selection, not additional card technologies.
                if kind == 1 and rate != 1:
                    continue
                result.append((kind, rate))
        return result

    def capabilities(self):
        """Verify Type 4 prerequisites on this actual connected reader."""
        kinds = C.POINTER(INT)()
        try:
            result = self.lib.nfc_device_get_supported_modulation(
                self.device, 0, C.byref(kinds))  # N_TARGET
            if result < 0:
                return {'target_mode': False, 'ndef_uri_emulation': False}
            advertised = []
            for index in range(16):
                kind = kinds[index]
                if not kind:
                    break
                advertised.append(kind)
            supported = 1 in advertised
            if not supported:
                return {'target_mode': False, 'ndef_uri_emulation': False}
            rates = C.POINTER(INT)()
            result = self.lib.nfc_device_get_supported_baud_rate_target_mode(
                self.device, 1, C.byref(rates))  # ISO14443A
            advertised_rates = []
            if result >= 0:
                for index in range(8):
                    rate = rates[index]
                    if not rate:
                        break
                    advertised_rates.append(rate)
            capable = 1 in advertised_rates
            return {'target_mode': True, 'ndef_uri_emulation': bool(capable)}
        except (AttributeError, ValueError, TypeError, OSError):
            return {'target_mode': None, 'ndef_uri_emulation': None}

    def identity(self):
        pointer = PTR()
        self._check(self.lib.nfc_device_get_information_about(self.device, C.byref(pointer)))
        try:
            text = C.string_at(pointer).decode('utf-8', 'replace')
        finally:
            self.lib.nfc_free(pointer)
        version = self.lib.nfc_version().decode('ascii', 'replace')
        info = parse_info(f'uses libnfc {version}\n{text}')
        for key, kind in (('iso_a', 1), ('iso_b', 3), ('felica', 7)):
            info[key] = 'Yes' if any(m[0] == kind for m in self.modulations) else 'No'
        return info

    def scan(self, modulation):
        kind, rate = modulation
        target = Target()
        operation = f'{NAMES.get(kind, kind)} baud={rate}'
        # A previous selection can leave a card halted and raw protocols change
        # framing, bitrate and modulation registers. Public initiator_init drops
        # the RF field and restores the initiator defaults before each attempt.
        # Reapply finite retries: initiator_init enables infinite selection.
        self._check(self.lib.nfc_initiator_init(self.device), operation + ' reset')
        self._check(self.lib.nfc_device_set_property_bool(self.device, 7, False),
                    operation + ' finite retries')
        if kind == 8:
            # Passive NFC-DEP peers, including all advertised baud rates.
            # Host timeout must allow firmware activation retries to finish;
            # an 80ms host timeout can expire before the chip's 103ms ATR timer.
            result = self.lib.nfc_initiator_select_dep_target(
                self.device, 1, rate, None, C.byref(target), 1000)
        else:
            result = self.lib.nfc_initiator_select_passive_target(
                self.device, Modulation(kind, rate), None, 0, C.byref(target))
        if result in (-2, -3, -8):
            # Firmware/driver advertises more than this particular reader can
            # activate. Report it; never silently drop a whole technology.
            return 'unsupported'
        if result in (0, -6, -10, -20):
            return None
        self._check(result, operation + ' select')
        # Publish the successful selection directly. The next RF reset releases
        # it, including raw protocols where InDeselect is ineffective. This also
        # avoids discarding a valid read because a later cleanup command failed.
        return decode_target(target)

    def abort(self):
        if self.device:
            self.lib.nfc_abort_command(self.device)

    def close(self):
        if self.device:
            self.lib.nfc_close(self.device)
            self.device = None
        if self.context:
            self.lib.nfc_exit(self.context)
            self.context = PTR()

class NFCTargetSession:
    """A separate, exclusive target-mode session; only NFCBackend owns it."""

    def __init__(self, settings):
        connection = settings.connection_string()
        self.lib = bind_library()
        self.context = PTR()
        self.device = None
        try:
            self.lib.nfc_init(C.byref(self.context))
            if not self.context:
                raise OSError('libnfc target context unavailable')
            self.device = self.lib.nfc_open(self.context, connection.encode('utf-8'))
            if not self.device:
                raise OSError('NFC target device unavailable')
        except BaseException:
            self.close()
            raise

    def serve_uri(self, url, cancelled, on_event):
        """Emulate a read-only Type 4 tag until complete/cancelled.

        Incomplete reads, timeouts and failed sends never emit transferred.
        libnfc target operations run solely on the backend worker.
        """
        from nfc_ndef import Type4UriTag
        tag = Type4UriTag(url)
        target = Target()
        target.modulation = Modulation(1, 0)  # ISO14443A / undefined bitrate
        target.info.a.atqa[:] = (0x00, 0x04)
        target.info.a.sak = 0x20  # ISO14443-4 compliant Type A
        target.info.a.uid_len = 4
        target.info.a.uid[:4] = (0x08, 0x00, 0xB0, 0x0B)  # Random UID prefix
        target.info.a.ats_len = 4
        target.info.a.ats[:4] = (0x75, 0x33, 0x92, 0x03)
        receive = (U8 * 264)()
        while not cancelled():
            n = self.lib.nfc_target_init(self.device, C.byref(target),
                                         receive, len(receive), 500)
            if n in (-6, -10, -20):
                continue
            if n < 0:
                raise OSError('NFC target activation failed (%d)' % n)
            on_event('share.phone_detected', {})
            while not cancelled():
                # libnfc can activate a target without delivering an APDU yet.
                # Do not reply with an error frame to an empty activation.
                if n == 0:
                    n = self.lib.nfc_target_receive_bytes(self.device, receive,
                                                           len(receive), 500)
                    if n in (-6, -10, -20):
                        break
                    if n < 0:
                        raise OSError('NFC target receive failed (%d)' % n)
                    continue
                packet = bytes(receive[:n])
                answer = tag.respond(packet)
                outgoing = (U8 * len(answer)).from_buffer_copy(answer)
                sent = self.lib.nfc_target_send_bytes(self.device, outgoing,
                                                       len(outgoing), 500)
                if sent < 0:
                    if sent in (-6, -10, -20):
                        break
                    raise OSError('NFC target send failed (%d)' % sent)
                if tag.sent():
                    on_event('share.ndef_transferred', {'url': url})
                    return True
                n = self.lib.nfc_target_receive_bytes(self.device, receive,
                                                       len(receive), 500)
                if n in (-6, -10, -20):
                    break
                if n < 0:
                    raise OSError('NFC target receive failed (%d)' % n)
            tag = Type4UriTag(url)  # Never mix coverage across phone sessions.
        return False

    def abort(self):
        if self.device:
            self.lib.nfc_abort_command(self.device)

    def close(self):
        if self.device:
            self.lib.nfc_close(self.device)
            self.device = None
        if self.context:
            self.lib.nfc_exit(self.context)
            self.context = PTR()
