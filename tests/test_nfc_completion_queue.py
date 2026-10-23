"""Completion wakeups remain bounded and reliable under input backpressure."""
import unittest
from unittest.mock import Mock
from ui_events import UIEventLoop, InputEvent


class CompletionQueueTests(unittest.TestCase):
    def loop(self):
        handler = Mock()
        return UIEventLoop(lambda: None, handler, lambda: None, lambda: None,
                           capacity=1), handler

    def test_full_input_queue_retains_each_nfc_completion_once(self):
        loop, handler = self.loop()
        press = InputEvent('press', 1, 0)
        self.assertTrue(loop.post(press))
        kinds = ('nfc_card', 'nfc_status', 'nfc_capabilities',
                 'nfc_emg_capture', 'nfc_spool_ready', 'nfc_gate_lookup',
                 'nfc_gate_verify', 'nfc_share_done', 'nfc_share_failed',
                 'nfc_share_cancelled')
        for kind in kinds:
            for value in range(20):
                self.assertTrue(loop.post_coalesced(InputEvent(kind, value, 0)))
        self.assertEqual(loop._queue.qsize(), 1)
        self.assertEqual(len(loop._coalesced), len(kinds))
        self.assertIs(loop._queue.get_nowait(), press)
        loop._queue.task_done()
        loop._drain_coalesced()
        self.assertEqual([c.args[0].kind for c in handler.call_args_list], list(kinds))
        self.assertTrue(all(c.args[0].value == 19 for c in handler.call_args_list))
        loop._drain_coalesced()
        self.assertEqual(handler.call_count, len(kinds))
        loop.close()
        self.assertFalse(loop.post_coalesced(InputEvent('nfc_card', 0, 0)))

    def test_completion_storage_is_bounded_and_reentrant_updates_survive(self):
        loop, handler = self.loop()
        for index in range(32):
            self.assertTrue(loop.post_coalesced(InputEvent(str(index), 0, 0)))
        self.assertFalse(loop.post_coalesced(InputEvent('overflow', 0, 0)))
        self.assertTrue(loop.post_coalesced(InputEvent('0', 1, 0)))
        handler.side_effect = lambda event: (
            loop.post_coalesced(InputEvent('next', 2, 0)) if event.kind == '0' else None)
        loop._drain_coalesced()
        self.assertEqual(tuple(loop._coalesced), ('next',))
        handler.side_effect = None
        loop._drain_coalesced()
        self.assertEqual(handler.call_args.args[0].kind, 'next')
        loop.close()
