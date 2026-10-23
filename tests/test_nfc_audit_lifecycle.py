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

    def test_enrollment_capture_survives_overlay_and_nested_power_dialog(self):
        for mode in ('waiting', 'spool_waiting'):
            for overlay in ('power', 'gate', 'nested'):
                with self.subTest(mode=mode, overlay=overlay):
                    view = display(snapshot())
                    view._uart_online = True
                    view.Draw_RFID_Menu = Mock()
                    view._rfid_mode = mode
                    view._nfc_gate_popup = {'origin': view.RFIDMenu}
                    view.checkkey = view.NFCGateMenu if overlay == 'gate' else view.PowerConfirm
                    view._power_origin = view.NFCGateMenu if overlay == 'nested' else view.RFIDMenu
                    future = view._rfid_assignment = Future()
                    self.assertTrue(view._rfid_context_active())
                    self.assertFalse(future.cancelled())
                    future.set_result({'uid': 'AA:BB'})
                    view._rfid_assignment_event()
                    self.assertEqual(view._rfid_candidate, {'uid': 'AA:BB'})
                    self.assertEqual(view._rfid_mode,
                                     'confirm' if mode == 'waiting' else 'spool_confirm')
                    view.Draw_RFID_Menu.assert_not_called()

    def test_real_navigation_cancels_capture_and_leaves_waiting_page(self):
        for mode, target in (('waiting', 'emg'), ('spool_waiting', 'spool_detail')):
            view = display(snapshot())
            view.checkkey = view.MainMenu
            view._rfid_mode = mode
            future = view._rfid_assignment = Future()
            self.assertFalse(view._rfid_context_active())
            view._rfid_cancel_assignment()
            self.assertTrue(future.cancelled())
            self.assertIsNone(view._rfid_assignment)
            self.assertEqual(view._rfid_mode, target)

    def test_spoolman_transport_survives_a_worker_close_timeout(self):
        view = display(snapshot())
        printer = view.pd
        class FinishingWorker:
            def __init__(self):
                self.callbacks = []
            def close(self):
                return False  # A started multi-request move is still running.
            def on_stopped(self, callback):
                self.callbacks.append(callback)
            def finish(self):
                for callback in self.callbacks:
                    callback()
        worker = printer._read_worker = FinishingWorker()
        printer.spoolman_client = Mock()
        printer.close()
        printer.spoolman_client.close.assert_not_called()
        # The started operation can still complete its link and readback.
        printer.spoolman_client.request('POST', '/server/spoolman/proxy', {})
        worker.finish()
        printer.spoolman_client.close.assert_called_once()
