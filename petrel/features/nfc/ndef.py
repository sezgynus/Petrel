"""Read-only NFC Forum Type 4 NDEF URI tag, ISO 7816-4 APDU model.

No GPIO, libnfc handles, or URL-opening policy belongs in this module.
Coverage is measured over the full NLEN + NDEF bytes, *after* a successful
target response send; transfer != browser navigation or link opening.
"""
from urllib.parse import urlsplit


AID_V2 = bytes.fromhex('D2760000850101')
AID_V1 = bytes.fromhex('D2760000850100')
# NFC Forum Type 4 Tag v2.0, read-only CC with bounded APDUs.
CC = bytes.fromhex('000F2000F000FF0406E104080000FF')


def ndef_uri_file(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise ValueError('Invalid NFC URI')
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
        raise ValueError('NFC URI must be HTTP(S)')
    raw = url.encode('utf-8')
    prefix = next(((p, marker) for p, marker in
                   (('https://', 0x04), ('http://', 0x03))
                   if url.startswith(p)), None)
    indicator, rest = (prefix[1], raw[len(prefix[0]):]) if prefix else (0, raw)
    payload = bytes((indicator,)) + rest
    if len(payload) < 256:
        record = b'\xD1\x01' + bytes((len(payload),)) + b'U' + payload
    else:
        record = b'\xC1\x01' + len(payload).to_bytes(4, 'big') + b'U' + payload
    if len(record) > 0x0800 - 2:
        raise ValueError('NDEF URI exceeds emulated tag capacity')
    return len(record).to_bytes(2, 'big') + record


class Type4UriTag:
    """One phone read session; issue immutable APDU responses."""

    def __init__(self, url):
        self.ndef = ndef_uri_file(url)
        self.selected = None
        self._ranges = bytearray(len(self.ndef))
        self.transferred = False
        self._pending = None

    def respond(self, apdu):
        self._pending = None
        if len(apdu) < 4 or apdu[0] != 0:
            return b'\x6E\x00'
        ins, p1, p2 = apdu[1:4]
        if ins == 0xA4:
            if len(apdu) < 5 or len(apdu) < 5 + apdu[4]:
                return b'\x67\x00'
            data = apdu[5:5 + apdu[4]]
            if p1 == 0x04 and data in (AID_V1, AID_V2):
                self.selected = None
                self._ranges = bytearray(len(self.ndef))
                self.transferred = False
                return b'\x90\x00'
            if p1 == 0 and data in (b'\xE1\x03', b'\xE1\x04'):
                self.selected = 'cc' if data[-1] == 3 else 'ndef'
                return b'\x90\x00'
            self.selected = None
            return b'\x6A\x82'
        if ins != 0xB0:
            return b'\x6D\x00'
        if self.selected is None or len(apdu) != 5:
            return b'\x69\x86'
        src = CC if self.selected == 'cc' else self.ndef
        offset = (p1 << 8) | p2
        n = apdu[4] or 256
        if offset >= len(src) or offset + n > len(src):
            return b'\x6B\x00'
        if self.selected == 'ndef':
            self._pending = (offset, offset + n)
        return src[offset:offset + n] + b'\x90\x00'

    def sent(self):
        """Call only after target_send_bytes acknowledges a response."""
        if self._pending is None:
            return False
        a, b = self._pending
        self._ranges[a:b] = b'\x01' * (b - a)
        self._pending = None
        if self._ranges and all(self._ranges):
            self.transferred = True
        return self.transferred
