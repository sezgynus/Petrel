"""NFC completion state survives temporary UI overlays (CI only)."""
from concurrent.futures import Future
import unittest
from unittest.mock import Mock

from test_capabilities import display, snapshot
from test_nfc_spool_tags import spool
from spoolman_tags import describe


class OverlayCompletionTests(unittest.TestCase):
    def test_spool_completion_is_retained_without_drawing_over_modal(self):
        for overlay in ('PowerConfirm', 'NFCGateMenu'):
            for outcome in ('page', 'saved', 'error', 'transfer'):
                with self.subTest(overlay=overlay, outcome=outcome):
                    view = display(snapshot())
                    view.checkkey = getattr(view, overlay)
                    view._uart_online = True
                    view.Draw_RFID_Menu = Mock()
                    view._rfid_mode = 'spool_loading' if outcome == 'page' else 'spool_saving'
                    future = view._spool_future = Future()
                    selected = describe(spool())
                    if outcome == 'page':
                        future.set_result(((selected,), False))
                    elif outcome == 'saved':
                        future.set_result('AA:BB')
                    elif outcome == 'error':
                        future.set_exception(ValueError('Unavailable'))
                    else:
                        namespace = view._spool_result_event.__func__.__globals__
                        future.set_exception(namespace['BindingConflict']('approved plan'))
                    view._spool_result_event()
                    self.assertEqual(view._rfid_mode, {
                        'page': 'spool_list', 'saved': 'spool_saved',
                        'error': 'spool_error', 'transfer': 'spool_transfer'}[outcome])
                    self.assertIsNone(view._spool_future)
                    view.Draw_RFID_Menu.assert_not_called()
                    if outcome == 'page':
                        self.assertEqual(view._spool_rows, (selected,))
                    if outcome == 'transfer':
                        self.assertEqual(view._spool_plan, 'approved plan')
                    # Reopening renders the completed state, without another write.
                    view.checkkey = view.RFIDMenu
                    view.Draw_RFID_Menu()
                    view.Draw_RFID_Menu.assert_called_once()
