"""Type 4 NDEF Android tag-dispatch lifetime; CI-only fake libnfc."""
import ctypes as C
import unittest
from unittest.mock import Mock

from petrel.features.nfc.libnfc import NFCTargetSession
from petrel.features.nfc.ndef import AID_V2, CC, ndef_uri_file


URL = 'https://github.com/sezgynus/Petrel'


def select(payload, by_name=False):
    return bytes((0x00, 0xA4, 0x04 if by_name else 0x00,
                  0x0C, len(payload))) + payload


def read(offset, size):
    return bytes((0x00, 0xB0, offset >> 8, offset & 255, size))


class Type4AndroidDispatchTests(unittest.TestCase):
    @staticmethod
    def session(frames, *, receive_codes=()):
        session = NFCTargetSession.__new__(NFCTargetSession)
        session.device = 100
        session._pn532_target = True
        session.lib = Mock()
        session.lib.pn53x_write_register.return_value = 0
        session.lib.nfc_target_init.return_value = 0
        session.lib.nfc_target_send_bytes.return_value = 0
        received = []
        responses = []
        frames = iter(frames)
        final_codes = iter(receive_codes)

        def recv(_dev, destination, _size, timeout):
            received.append(timeout)
            try:
                packet = next(frames)
            except StopIteration:
                return next(final_codes, -6)
            if isinstance(packet, int):
                return packet
            C.memmove(destination, packet, len(packet))
            return len(packet)

        def send(_dev, response, size, timeout):
            responses.append(bytes(response[:size]))
            self_check = timeout == 500
            assert self_check
            return 0

        session.lib.nfc_target_receive_bytes.side_effect = recv
        session.lib.nfc_target_send_bytes.side_effect = send
        return session, received, responses

    def test_full_ndef_is_not_followed_by_immediate_target_teardown(self):
        data = ndef_uri_file(URL)
        frames = (
            select(AID_V2, True),
            select(b'\xE1\x03'),
            read(0, len(CC)),
            select(b'\xE1\x04'),
            read(0, len(data)),
            # Android may perform further reads after NDEF tag detection.
            select(b'\xE1\x04'),
            read(0, len(data)),
        )
        session, timeouts, responses = self.session(frames)
        emitted = []
        result = session.serve_uri(URL, lambda: False,
                                   lambda event, payload: emitted.append(event))
        self.assertTrue(result)
        self.assertEqual(emitted.count('share.ndef_transferred'), 1)
        self.assertEqual(emitted.count('share.phone_detected'), 1)
        self.assertEqual(responses[-1], data + b'\x90\x00')
        self.assertEqual(responses[-3], data + b'\x90\x00')
        self.assertEqual(len(responses), len(frames))
        self.assertEqual(timeouts[:5], [500] * 5)
        self.assertTrue(all(value == 2000 for value in timeouts[5:]))

    def test_incomplete_ndef_timeout_does_not_report_success(self):
        session, timeouts, responses = self.session((
            select(AID_V2, True),
            select(b'\xE1\x04'),
            read(0, 2),  # NLEN alone cannot complete NDEF transfer.
        ))
        cancelled = [False]
        def recv_and_cancel(device, buffer, length, timeout):
            result = original(device, buffer, length, timeout)
            if result == -6:
                cancelled[0] = True
            return result
        original = session.lib.nfc_target_receive_bytes.side_effect
        session.lib.nfc_target_receive_bytes.side_effect = recv_and_cancel
        events = []
        self.assertFalse(session.serve_uri(URL, lambda: cancelled[0],
                                           lambda event, _: events.append(event)))
        self.assertNotIn('share.ndef_transferred', events)
        self.assertTrue(all(value == 500 for value in timeouts))

    def test_after_success_phone_release_is_normal_completion(self):
        data = ndef_uri_file(URL)
        frames = (select(AID_V2, True), select(b'\xE1\x04'),
                  read(0, len(data)), -1)
        session, timeouts, _ = self.session(frames)
        events = []
        self.assertTrue(session.serve_uri(URL, lambda: False,
                                          lambda event, _: events.append(event)))
        self.assertEqual(events.count('share.ndef_transferred'), 1)
        self.assertEqual(timeouts[-1], 2000)
