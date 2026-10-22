"""Broker startup lifetime and lazy diagnostics contracts (CI only)."""
import argparse
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
import weakref
from unittest.mock import patch

from dwin_broker import parse_arguments

ROOT = Path(__file__).resolve().parents[1]


class BrokerStartupTests(unittest.TestCase):
    def test_parser_is_released_before_entering_the_service_loop(self):
        references = []
        original = argparse.ArgumentParser.parse_args

        def track(parser, argv=None, namespace=None):
            references.append(weakref.ref(parser))
            return original(parser, argv, namespace)

        with patch.object(argparse.ArgumentParser, 'parse_args', track):
            args = parse_arguments(['--port', '/dev/ttyAMA0'])
        self.assertEqual(args.port, '/dev/ttyAMA0')
        self.assertEqual(args.backend, '/dev/dwin-uart-backend')
        self.assertEqual(args.socket, '/run/petrel-dwin/display.sock')
        self.assertIsNone(references[0]())

    def test_custom_options_and_equals_syntax_remain_supported(self):
        args = parse_arguments(['--port=/dev/ttyS0', '--backend', '/dev/test-backend',
                                '--socket', '/run/test/display.sock'])
        self.assertEqual(vars(args), dict(port='/dev/ttyS0', backend='/dev/test-backend',
                                         socket='/run/test/display.sock'))

    def test_help_and_invalid_cli_exit_before_starting_transport(self):
        for argv, status, expected in [
                (['--help'], 0, '--backend'),
                ([], 2, '--port'),
                (['--port', '/dev/nonexistent', '--unknown'], 2, 'unrecognized arguments'),
                (['--port'], 2, 'expected one argument')]:
            with self.subTest(argv=argv):
                result = subprocess.run([sys.executable, 'dwin_broker.py', *argv],
                                        cwd=ROOT, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout + result.stderr)

    def test_healthy_startup_skips_logging_and_fault_keeps_original_traceback(self):
        # A fresh interpreter is essential: unittest imports logging itself.
        script = textwrap.dedent('''
            import sys
            from dwin_broker import parse_arguments
            from dwin_aux_backend import AuxBackend
            from dwin_diagnostics import log_exception
            parse_arguments(['--port', '/dev/ttyAMA0'])
            assert 'logging' not in sys.modules, 'logging loaded during healthy startup'
            for name in ('dwin_broker', 'dwin_aux_backend'):
                try:
                    raise RuntimeError('original fault ' + name)
                except RuntimeError:
                    log_exception(name, 'transport failed (%s)', 'test')
            assert 'logging' in sys.modules
        ''')
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ('dwin_broker', 'dwin_aux_backend'):
            self.assertIn(f'ERROR:{name}:transport failed (test)', result.stderr)
            self.assertIn(f'RuntimeError: original fault {name}', result.stderr)
        self.assertEqual(result.stderr.count('Traceback (most recent call last):'), 2)


if __name__ == '__main__':
    unittest.main()
