import unittest
from unittest.mock import Mock

import petrel.printer.interface as backend


class PowerDeviceTests(unittest.TestCase):
    def printer(self, status='on', name='Printer'):
        result = backend.PrinterData.__new__(backend.PrinterData)
        result.power_device = 'Printer'
        result.client = Mock()
        result.client.get.return_value = {
            'result': {'devices': [{'device': name, 'status': status}]}
        }
        result.client.post.return_value = object()
        return result

    def test_power_off_posts_only_when_configured_device_is_on(self):
        result = self.printer('on', 'printer')
        result.power_off_if_on()
        path, payload = result.client.post.call_args.args[:2]
        guard = result.client.post.call_args.kwargs['guard']
        self.assertEqual(path, '/machine/device_power/device')
        self.assertTrue(guard())
        self.assertEqual(payload, {'device': 'printer', 'action': 'off'})
        self.assertFalse(result.client.post.call_args.kwargs['report_error'])

    def test_power_off_guard_rejects_non_on_states_and_missing_device(self):
        for status in ('off', 'init', 'error'):
            with self.subTest(status=status):
                result = self.printer(status)
                result.power_off_if_on()
                guard = result.client.post.call_args.kwargs['guard']
                with self.assertRaises(backend.MoonrakerError):
                    guard()
        result = self.printer('on', 'Other')
        result.power_off_if_on()
        with self.assertRaises(backend.MoonrakerError):
            result.client.post.call_args.kwargs['guard']()


if __name__ == '__main__':
    unittest.main()
