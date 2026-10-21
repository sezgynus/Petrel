"""Direct public libnfc ABI. Packed layouts mirror nfc/nfc-types.h (1.8)."""
import ctypes as C
import ctypes.util
import os

from nfc_info import DEFAULT_DEVICE, parse_info

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


def bind_library():
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
    }
    for name, (result, args) in signatures.items():
        function = getattr(lib, name)
        function.restype, function.argtypes = result, args
    return lib


class NFCSession:
    """One device handle, all supported passive card technologies, no CLI tools."""
    def __init__(self):
        self.lib = bind_library()
        self.context, self.device = PTR(), None
        try:
            self.lib.nfc_init(C.byref(self.context))
            if not self.context:
                raise OSError('libnfc context unavailable')
            connection = os.environ.get('PETREL_NFC_DEVICE', DEFAULT_DEVICE)
            self.device = self.lib.nfc_open(self.context, connection.encode())
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
