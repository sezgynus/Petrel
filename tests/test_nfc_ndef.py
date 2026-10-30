"""NDEF read-only tag protocol contracts; no NFC hardware or emulator."""
import unittest

from petrel.features.nfc.ndef import AID_V2, CC, Type4UriTag, ndef_uri_file


def select(payload, by_name=False):
    return bytes((0, 0xA4, 4 if by_name else 0, 0, len(payload))) + payload


def read(offset, size):
    return bytes((0, 0xB0, offset >> 8, offset & 255, size))


class NDEFTests(unittest.TestCase):
    def test_uri_record_and_input_bounds(self):
        file = ndef_uri_file('https://example.org/guide')
        self.assertEqual(int.from_bytes(file[:2], 'big'), len(file) - 2)
        self.assertEqual(file[2:6], b'\xD1\x01\x12U')
        self.assertEqual(file[6], 4)
        for value in ('file:///tmp/password', 'javascript:alert(1)',
                      'https://host/\nCR', '', 'http://'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ndef_uri_file(value)
        large = ndef_uri_file('https://example.org/' + 'x' * 400)
        self.assertEqual(large[2], 0xC1)

    def test_coverage_requires_ndef_bytes_successfully_sent(self):
        tag = Type4UriTag('https://example.org/')
        self.assertEqual(tag.respond(select(AID_V2, True)), b'\x90\x00')
        self.assertEqual(tag.respond(select(b'\xE1\x03')), b'\x90\x00')
        self.assertEqual(tag.respond(read(0, 15)), CC + b'\x90\x00')
        self.assertFalse(tag.sent())
        self.assertEqual(tag.respond(select(b'\xE1\x04')), b'\x90\x00')
        length = len(tag.ndef)
        self.assertEqual(tag.respond(read(0, length)), tag.ndef + b'\x90\x00')
        self.assertFalse(tag.transferred)
        self.assertTrue(tag.sent())
        self.assertTrue(tag.transferred)

    def test_partial_out_of_order_reads_and_invalid_apdu(self):
        tag = Type4UriTag('https://example.org/path')
        self.assertEqual(tag.respond(read(0, 2)), b'\x69\x86')
        tag.respond(select(AID_V2, True))
        tag.respond(select(b'\xE1\x04'))
        n = len(tag.ndef)
        self.assertEqual(tag.respond(read(n, 1)), b'\x6B\x00')
        self.assertEqual(tag.respond(b'\x00\xD6\x00\x00\x00'), b'\x6D\x00')
        tag.respond(read(2, n - 2))
        self.assertFalse(tag.sent())
        tag.respond(read(0, 2))
        self.assertTrue(tag.sent())
        tag.respond(select(AID_V2, True))
        self.assertFalse(tag.sent())
        self.assertFalse(tag.transferred)
        self.assertFalse(any(tag._ranges))
