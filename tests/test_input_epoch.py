from unittest.mock import Mock
import unittest

from test_capabilities import display, printer, snapshot
from petrel.ui.events import InputEvent


class InputEpochTests(unittest.TestCase):
    def panel(self):
        result = display(snapshot())
        result._closed = False
        result._encoder_event = result.ENCODER_DIFF_NO
        result._dispatch_input = Mock()
        result.HMI_StartFrame = Mock()
        return result

    def test_new_epoch_refreshes_state_and_discards_captured_menu_action(self):
        result = self.panel()
        data = snapshot()
        data['epoch'] = 2
        result.pd.subscription.snapshot.return_value = data
        result._process_input(InputEvent('press', 1, 2))
        self.assertEqual(result.pd.state.epoch, 2)
        result._dispatch_input.assert_not_called()
        result.HMI_StartFrame.assert_called_once_with(False)
        result._process_input(InputEvent('press', 1, 2))
        result._dispatch_input.assert_called_once()

    def test_active_extruder_change_discards_old_editor_action(self):
        result = self.panel()
        result.pd.subscription.snapshot.return_value = snapshot(multiple=True)
        result._process_input(InputEvent('press', 1, 1))
        result._dispatch_input.assert_not_called()
        self.assertEqual(result.pd.capabilities.active_hotend.name, 'extruder1')

    def test_current_position_is_refreshed_before_dispatch(self):
        result = self.panel()
        data = snapshot()
        data['status']['gcode_move']['position'][0] = 50
        result.pd.subscription.snapshot.return_value = data
        seen = []
        result._dispatch_input.side_effect = lambda: seen.append(result.pd.state.status['gcode_move']['position'][0])
        result._process_input(InputEvent('press', 1, 1))
        self.assertEqual(seen, [50])

    def test_backend_rejects_stale_epoch_before_enqueuing(self):
        result = printer(snapshot())
        data = snapshot()
        data['epoch'] = 2
        result.subscription.snapshot.return_value = data
        future = result.postREST('/printer/gcode/script', {'script': 'G28'})
        self.assertIsNotNone(future.exception())
        result.client.post.assert_not_called()
