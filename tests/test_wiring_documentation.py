"""Keep the visible default wiring diagram aligned with installer defaults."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


class DefaultWiringDocumentationTests(unittest.TestCase):
    def test_visible_encoder_pin_labels_match_kconfig_and_header_positions(self):
        tree = ET.parse(ROOT / 'images/petrel-wiring.svg')
        by_id = {element.get('id'): element for element in tree.iter() if element.get('id')}
        kconfig = (ROOT / 'Kconfig').read_text(encoding='utf-8')
        physical = {16: 36, 19: 35, 20: 38, 21: 40}
        for label, symbol, kind in (
                ('encoder-a', 'ENCODER_A_GPIO', 'encoder'),
                ('encoder-b', 'ENCODER_B_GPIO', 'encoder'),
                ('encoder-button', 'PETREL_BUTTON_PIN', 'button')):
            with self.subTest(signal=label):
                section = re.search(r'(?ms)^config ' + symbol + r'\n(.*?)(?=^config |^endmenu|\Z)', kconfig)
                self.assertIsNotNone(section)
                default = int(re.search(r'^\s+default (\d+)', section.group(1), re.MULTILINE).group(1))
                shown_bcm = ''.join(by_id[label + '-bcm'].itertext())
                shown_physical = int(''.join(by_id[label + '-physical'].itertext()))
                self.assertEqual(shown_bcm, 'GPIO' + str(default))
                self.assertEqual(shown_physical, physical[default])
                self.assertEqual(by_id['pin-' + str(shown_physical)].get('class'), kind)
        self.assertEqual(''.join(by_id['uart-tx-bcm'].itertext()), 'GPIO14 / TX')
        self.assertEqual(''.join(by_id['uart-rx-bcm'].itertext()), 'GPIO15 / RX')
        self.assertIn('Display RX', ''.join(by_id['uart-tx-connection'].itertext()))
        self.assertIn('Display TX', ''.join(by_id['uart-rx-connection'].itertext()))
        self.assertEqual(by_id['pin-35'].get('class'), 'buzzer')
