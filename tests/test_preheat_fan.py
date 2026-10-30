import unittest
from unittest.mock import Mock
import petrel.printer.interface as backend


class PreheatFanTests(unittest.TestCase):
    def test_preset_preheat_does_not_change_part_fan(self):
        result = backend.PrinterData.__new__(backend.PrinterData)
        result.material_preset = [backend.material_preset_t('PLA', 200, 60)]
        result.preHeat = Mock(return_value='future')
        returned = result.preheat('PLA')
        self.assertEqual(returned, 'future')
        result.preHeat.assert_called_once_with(60, 200)

    def test_unknown_preset_is_rejected(self):
        result = backend.PrinterData.__new__(backend.PrinterData)
        result.material_preset = []
        with self.assertRaises(ValueError):
            result.preheat('unknown')


if __name__ == '__main__':
    unittest.main()
