import unittest

from petrel.hardware.dwin.protocol import TAIL, aux_baud_divisor, aux_frames, take_response


class SharedProtocolTests(unittest.TestCase):
    def test_auxiliary_binary_chunk_boundaries_preserve_every_byte(self):
        for prefix in (0, 1, 243, 244, 245, 246, 247, 248, 249, 496):
            data = b'x' * prefix + TAIL * 3 + bytes(range(256)) * 2
            with self.subTest(prefix=prefix):
                frames = list(aux_frames(data))
                self.assertEqual(b''.join(f[2:-4] for f in frames), data)
                self.assertTrue(all(6 < len(f) <= 254 for f in frames))
                self.assertTrue(all(TAIL not in f[2:-4] for f in frames))
        self.assertEqual(list(aux_frames(b'')), [])

    def test_fragmented_upload_keeps_embedded_header_and_trailer(self):
        data = b'\xaa' + TAIL + b'\x00\xff'
        frame = b'\xaa\x3a' + bytes([len(data)]) + data + TAIL
        for cut in range(1, len(frame)):
            buffer = bytearray(frame[:cut])
            self.assertIsNone(take_response(buffer))
            buffer.extend(frame[cut:])
            self.assertEqual(take_response(buffer), (0x3a, bytes([len(data)]) + data))
            self.assertEqual(buffer, b'')

    def test_memory_reply_does_not_consume_following_aux_upload(self):
        data = b'\xaa' + TAIL
        payload = b'\x5a\x00\x10' + bytes([len(data)]) + data
        buffer = bytearray(b'noise\xaa\x32' + payload + TAIL
                           + b'\xaa\x3a\x01x' + TAIL)
        self.assertEqual(take_response(buffer), (0x32, payload))
        self.assertEqual(take_response(buffer), (0x3a, b'\x01x'))
        self.assertIsNone(take_response(buffer))

    def test_bad_trailer_and_unknown_opcode_resynchronize(self):
        buffer = bytearray(b'\xaa\x99noise\xaa\x00NOxxxx'
                           + b'\xaa\x00OK' + TAIL)
        self.assertEqual(take_response(buffer), (0x00, b'OK'))
        self.assertEqual(buffer, b'')

    def test_baud_divisor_matches_existing_panel_calculation(self):
        self.assertEqual(aux_baud_divisor(115200), (136, 115200))
        self.assertEqual(aux_baud_divisor(19200), (816, 19200))
        for value in (0, 9600, -1, 115200.0, 100000000):
            with self.assertRaises(ValueError):
                aux_baud_divisor(value)


if __name__ == '__main__':
    unittest.main()
