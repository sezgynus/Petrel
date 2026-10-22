from pathlib import Path
import re
import unittest


class RequirementPinTests(unittest.TestCase):
    def test_runtime_requirements_are_exactly_pinned(self):
        requirements = (
            Path(__file__).resolve().parents[1] / 'requirements.txt'
        ).read_text(encoding='utf-8').splitlines()
        pins = [line.strip() for line in requirements
                if line.strip() and not line.lstrip().startswith('#')]
        self.assertTrue(pins)
        for requirement in pins:
            self.assertRegex(
                requirement,
                r'^[A-Za-z0-9_.-]+==[^=<>!~\s]+$',
                msg='Runtime dependencies must use exact versions: ' + requirement,
            )

    def test_configurator_bootstrap_pin_matches_installed_dependency(self):
        root = Path(__file__).resolve().parents[1]
        config = (root / 'requirements-config.txt').read_text().strip()
        self.assertRegex(config, r'^kconfiglib==[^=<>!~\s]+$')
        self.assertIn(config, (root / 'requirements.txt').read_text().splitlines())

    def test_expected_runtime_dependencies_are_present(self):
        requirements = (
            Path(__file__).resolve().parents[1] / 'requirements.txt'
        ).read_text(encoding='utf-8')
        names = {
            re.split(r'==', line.strip(), maxsplit=1)[0].lower()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith('#')
        }
        self.assertEqual(
            names,
            {'gpiozero', 'lgpio', 'pyserial', 'websocket-client', 'pillow', 'qrcode', 'kconfiglib'},
        )


if __name__ == '__main__':
    unittest.main()
