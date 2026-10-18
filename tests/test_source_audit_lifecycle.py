"""Operation progress and shutdown ordering; executed by branch CI only."""
from concurrent.futures import Future
from threading import Event, Thread
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import unittest
from test_capabilities import display, snapshot
from test_regressions import ui, backend
from moonraker_subscription import MoonrakerSubscription


class AuditLifecycleTests(unittest.TestCase):
    def test_maintenance_advances_before_hold_popup_and_uart_early_returns(self):
        for mode in ('hold', 'popup', 'uart'):
            with self.subTest(mode=mode):
                v = ui.PetrelDisplay.__new__(ui.PetrelDisplay)
                v.pd = Mock()
                v.pd.maintenance_pulse.pending = True
                v.pd.maintenance_reader.pending = False
                v._uart_online = mode != 'uart'
                v.lcd = Mock()
                v._poll_panel_power = Mock()
                v._sync_case_light_tracking = Mock()
                v._ensure_uart = Mock()
                v._next_uart_probe = float('inf')
                v._power_hold_tick = Mock(return_value=mode == 'hold')
                v._power_popup_tick = Mock(return_value=mode == 'popup')
                v._advance_maintenance_operations = Mock()
                v._ui_tick()
                v._advance_maintenance_operations.assert_called_once_with()
                v.pd.update_variable.assert_called()

    def test_hidden_completion_is_presented_after_overlay(self):
        v = display(snapshot())
        v._maintenance_init()
        v.checkkey = v.PowerConfirm
        result = NS(status='OBSERVED')
        v.pd.maintenance_pulse = NS(pending=True, phase='running')
        v.pd.poll_maintenance_physical = Mock(return_value=result)
        v._advance_maintenance_operations()
        self.assertIs(v._maintenance_pending_result, result)
        v.pd.maintenance_pulse.pending = False
        v.checkkey = v.MaintenanceMenu
        v._maintenance_complete = Mock()
        v._poll_maintenance_ui()
        v._maintenance_complete.assert_called_once_with(result)

    def test_emergency_barrier_waits_for_writer_completion(self):
        s = MoonrakerSubscription('http://localhost:7125', autostart=False)
        s._state, s._socket = 'ready', Mock()
        f = s.request('printer.emergency_stop')
        entered = Event()
        def writer():
            entered.set()
            s._drain_outbound()
            s._notification({'id': s._id, 'result': {}})
        t = Thread(target=writer)
        t.start()
        self.assertTrue(entered.wait(1))
        self.assertTrue(s.wait_for_emergency_requests(timeout=1))
        self.assertTrue(f.done())
        t.join(1)
        s.close()

    def test_barrier_reports_unconfirmed_without_replay(self):
        s = MoonrakerSubscription('http://localhost:7125', autostart=False)
        s._state, s._socket = 'ready', Mock()
        f = s.request('printer.emergency_stop')
        self.assertFalse(s.wait_for_emergency_requests(timeout=0))
        self.assertEqual(s._outbound.qsize(), 1)
        s._socket.send.assert_not_called()
        s.close()
        self.assertTrue(f.done())

    def test_backend_closes_transport_after_safety_barrier(self):
        p = display(snapshot()).pd
        order = []
        p.maintenance_pulse.close = lambda: order.append('cancel')
        p.subscription.wait_for_emergency_requests = lambda **kw: order.append('barrier') or True
        p.subscription.close = lambda: order.append('transport')
        p.close()
        self.assertEqual(order, ['cancel', 'barrier', 'transport'])
