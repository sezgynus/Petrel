import json
import unittest
from unittest.mock import Mock
from urllib.error import URLError

from petrel.moonraker.client import MoonrakerClient, MoonrakerError
from test_moonraker_client import response
from test_capabilities import printer, snapshot, display
from test_regressions import backend


class JogRecoveryTests(unittest.TestCase):
    def setup_printer(self, effects):
        result = printer(snapshot())
        result.sendGCode = backend.PrinterData.sendGCode.__get__(result)
        opener = Mock()
        opener.open.side_effect = effects
        result.client = MoonrakerClient(opener=opener, timeout=.1)
        self.addCleanup(result.client.close)
        return result, opener

    def scripts(self, opener):
        return [json.loads(call.args[0].data)['script'] for call in opener.open.call_args_list]

    def test_motion_failure_restores_without_replaying_and_keeps_error(self):
        result, opener = self.setup_printer([response({'result': 'ok'}),
            response({'error': {'message': 'move rejected'}}), response({'result': 'ok'})])
        future = result.moveRelative('X', 1, 300)
        with self.assertRaises(MoonrakerError):
            future.result(2)
        scripts = self.scripts(opener)
        self.assertEqual(len(scripts), 3)
        self.assertTrue(scripts[0].startswith('SAVE_GCODE_STATE NAME=_PETREL_JOG_'))
        self.assertEqual(scripts[2], 'RESTORE_GCODE_STATE NAME=' + scripts[0].split('NAME=')[1] + ' MOVE=0')
        self.assertEqual(sum('G1 X1 F300' in script for script in scripts), 1)
        self.assertFalse(result.jog_recovery_required)

    def test_save_timeout_never_mutates_modes_or_restores_stale_state(self):
        result, opener = self.setup_printer([URLError('timeout')])
        with self.assertRaises(MoonrakerError):
            result.moveRelative('X', 1, 300).result(2)
        self.assertEqual(len(self.scripts(opener)), 1)
        self.assertFalse(result.jog_recovery_required)

    def test_restore_failure_blocks_motion_until_explicit_recovery(self):
        result, opener = self.setup_printer([response({'result': 'ok'}), URLError('timeout'),
            URLError('restore timeout'), response({'result': 'ok'})])
        with self.assertRaises(MoonrakerError):
            result.moveRelative('X', 1, 300).result(2)
        self.assertTrue(result.jog_recovery_required)
        for action in (lambda: result.moveRelative('Y', 1, 300),
                       lambda: result.sendGCode('G28'), result.resume_job,
                       lambda: result.openAndPrintFile('x.gcode')):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(opener.open.call_count, 3)
        result.restore_jog_state().result(2)
        self.assertFalse(result.jog_recovery_required)
        self.assertTrue(self.scripts(opener)[-1].startswith('RESTORE_GCODE_STATE'))
        self.assertTrue(self.scripts(opener)[-1].endswith('MOVE=0'))

    def test_success_reuses_one_saved_slot_and_preserves_full_restore(self):
        result, opener = self.setup_printer([response({'result': 'ok'})] * 4)
        result.moveRelative('X', 1, 300).result(2)
        result.moveRelative('Y', 1, 300).result(2)
        scripts = self.scripts(opener)
        self.assertEqual(scripts[0], scripts[2])
        self.assertIn('G91\nM83\nM220 S100\nM221 S100', scripts[1])
        self.assertFalse(result.jog_recovery_required)

    def test_epoch_change_after_save_prevents_mutation(self):
        result, opener = self.setup_printer([])
        def save(*args, **kwargs):
            data = snapshot()
            data['epoch'] = 2
            result.subscription.snapshot.return_value = data
            return response({'result': 'ok'})
        opener.open.side_effect = save
        with self.assertRaises(MoonrakerError):
            result.moveRelative('X', 1, 300).result(2)
        self.assertEqual(opener.open.call_count, 1)
        self.assertFalse(result.jog_recovery_required)

    def test_recovery_menu_and_thermal_shutdown_remain_available(self):
        result, opener = self.setup_printer([response({'result': 'ok'})])
        result._jog_restore = 'RESTORE_GCODE_STATE NAME=test MOVE=0'
        result.cooldown().result(2)
        self.assertIn('TURN_OFF_HEATERS', self.scripts(opener)[0])
        panel = display(snapshot())
        panel.pd._jog_restore = result._jog_restore
        panel._configure_menus()
        self.assertIn('RECOVERY', [key for key, _, _ in panel._menus['control']])

    def test_disconnect_during_mutation_does_not_restore_into_new_epoch(self):
        result, opener = self.setup_printer([])
        count = 0
        def respond(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 1:
                return response({'result': 'ok'})
            data = snapshot()
            data['epoch'] = 2
            result.subscription.snapshot.return_value = data
            raise URLError('disconnected')
        opener.open.side_effect = respond
        with self.assertRaises(MoonrakerError):
            result.moveRelative('X', 1, 300).result(2)
        self.assertEqual(opener.open.call_count, 2)
        self.assertTrue(result.jog_recovery_required)

    def test_closed_client_rejects_jog_without_leaving_restore_block(self):
        result, opener = self.setup_printer([])
        result.client.close()
        with self.assertRaises(MoonrakerError):
            result.moveRelative('X', 1, 300).result(2)
        opener.open.assert_not_called()
        self.assertFalse(result.jog_recovery_required)

    def test_rejected_backend_submission_cannot_change_modes(self):
        result, opener = self.setup_printer([])
        data = snapshot()
        data['epoch'] = 2
        result.subscription.snapshot.return_value = data
        with self.assertRaises(backend.MoonrakerError):
            result.moveRelative('X', 1, 300).result(2)
        opener.open.assert_not_called()
        self.assertFalse(result.jog_recovery_required)

    def test_cancelled_explicit_restore_keeps_unknown_state_block(self):
        from concurrent.futures import Future
        result, opener = self.setup_printer([])
        result._jog_restore = 'RESTORE_GCODE_STATE NAME=test MOVE=0'
        future = Future()
        future.cancel()
        result.postREST = Mock(return_value=future)
        result.restore_jog_state()
        self.assertTrue(result.jog_recovery_required)
