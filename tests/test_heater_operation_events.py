"""Completion cycles share dashboard readiness, without new polling."""
import json
from concurrent.futures import Future
from threading import Event
from unittest import TestCase
from unittest.mock import Mock
from heater_events import HeaterEvents, heater_ready
from buzzer_notifications import contains_homing
from moonraker_client import MoonrakerClient, MoonrakerError
from moonraker_subscription import MoonrakerSubscription


class HeaterCycleTests(TestCase):
    def test_heating_is_once_per_target_and_uses_dashboard_hysteresis(self):
        tracker = HeaterEvents()
        def sample(t, target=200):
            return tracker.update('extruder', {'temperature':t, 'target':target})
        self.assertEqual(sample(20), ())
        self.assertEqual(sample(197), ())
        self.assertEqual(sample(198), ('HEATING_DONE',))
        self.assertTrue(heater_ready(202.8,200,True))
        self.assertFalse(heater_ready(202.8,200,False))
        self.assertEqual(sample(204), ())
        self.assertEqual(sample(198), ())
        self.assertEqual(sample(198,220), ())
        self.assertEqual(sample(218,220), ('HEATING_DONE',))
        self.assertEqual(sample(218,220), ())

    def test_cooling_requires_zero_target_observed_heat_and_strict_crossing(self):
        tracker = HeaterEvents()
        def sample(t, target=0):
            return tracker.update('extruder', {'temperature':t,'target':target})
        self.assertEqual(sample(25), ())
        self.assertEqual(sample(49), ())
        self.assertEqual(sample(100,100), ())
        self.assertEqual(sample(60), ())
        self.assertEqual(sample(50), ())
        self.assertEqual(sample(49.9), ('COOLING_DONE',))
        self.assertEqual(sample(51), ())
        self.assertEqual(sample(49), ())
        self.assertEqual(sample(80,80), ())
        self.assertEqual(sample(30), ('COOLING_DONE',))

    def test_each_heater_has_independent_cycles_and_invalid_data_resets(self):
        tracker = HeaterEvents()
        for name in ('extruder', 'extruder1', 'heater_bed', 'heater_generic chamber'):
            self.assertEqual(tracker.update(name, {'temperature':90,'target':0}), ())
        self.assertEqual(tracker.update('heater_bed', {'temperature':45,'target':0}), ())
        self.assertEqual(tracker.update('extruder', {'temperature':45,'target':0}), ('COOLING_DONE',))
        self.assertEqual(tracker.update('heater_bed', {'temperature':39,'target':0}), ('COOLING_DONE',))
        self.assertEqual(tracker.update('extruder1', {'temperature':45,'target':0}), ('COOLING_DONE',))
        self.assertEqual(tracker.update('heater_generic chamber', {'temperature':45,'target':0}), ('COOLING_DONE',))
        tracker.update('extruder', {'temperature':20,'target':200})
        self.assertEqual(tracker.update('extruder', {'temperature':float('nan'),'target':200}), ())
        self.assertEqual(tracker.update('extruder', {'temperature':200,'target':200}), ())
        tracker.reset()
        self.assertEqual(tracker.update('extruder', {'temperature':200,'target':200}), ())

    def test_websocket_deltas_generate_events_without_requests(self):
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        observer = Mock()
        sub.set_melody_callback(observer)
        sub.request = Mock()
        sub._merge({'extruder': {'temperature':25,'target':200}},1,replace=True)
        sub._state = 'ready'
        sub._merge({'extruder': {'temperature':198}},2)
        sub._merge({'extruder': {'target':0}},3)
        sub._merge({'extruder': {'temperature':49}},4)
        self.assertEqual([c.args[0] for c in observer.call_args_list], ['HEATING_DONE','COOLING_DONE'])
        sub.request.assert_not_called()
        sub._invalidate('network lost')
        sub._merge({'extruder': {'temperature':200,'target':200}},5,replace=True)
        sub._state = 'ready'
        sub._merge({'extruder': {'temperature':200}},6)
        self.assertEqual(observer.call_count,2)

    def test_generic_temperature_subscription_does_not_retain_unleased_power(self):
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        sub._base_subscription = {'heater_generic chamber':['temperature','target']}
        sub._merge({'heater_generic chamber':{'temperature':25,'target':60,'power':.5}},1)
        self.assertEqual(sub.snapshot()['status']['heater_generic chamber'], {'temperature':25,'target':60})

    def test_bootstrap_subscribes_generic_heat_but_power_still_uses_lease(self):
        from test_subscription import FakeSocket
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        connection = FakeSocket(snapshot={
            'toolhead':{}, 'gcode_move':{}, 'print_stats':{'state':'standby'},
            'virtual_sdcard':{}, 'webhooks':{'state':'ready'},
            'heater_generic chamber':{'temperature':25,'target':60,'power':.5}})
        sub._socket = connection
        sub._bootstrap()
        self.assertEqual(sub._base_subscription['heater_generic chamber'], ['temperature','target'])
        # Usage tracking may independently retain power; remove that lease here.
        sub._usage_fields.pop('heater_generic chamber', None)
        sub._prune_thermal_status()
        self.assertNotIn('power',sub.snapshot()['status']['heater_generic chamber'])
        sub._settings['heater_generic chamber'] = {'heater_pin':'PA1'}
        sub.request = Mock(side_effect=lambda *a, **k:Future())
        sub.set_thermal_tracking(True)
        self.assertEqual(sub.request.call_args.args[1]['objects']['heater_generic chamber'],
                         ['temperature','target','power'])
        sub.set_thermal_tracking(False)
        self.assertEqual(sub.request.call_args.args[1]['objects']['heater_generic chamber'],
                         ['temperature','target'])


class OperationEventTests(TestCase):
    def test_homing_matches_commands_not_comments_and_runs_after_guarded_ws_send(self):
        self.assertFalse(contains_homing('; G28\nG1 X10'))
        self.assertFalse(contains_homing('M118 G28'))
        self.assertTrue(contains_homing('g28 x y ; home\nM400'))
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        sub._state, sub._epoch, sub._socket = 'ready',4,Mock()
        observer = Mock()
        sub.set_melody_callback(observer)
        sub.request('printer.gcode.script', {'script':'G28 X\nG28 Y'}, guard=lambda:False)
        sub._drain_outbound()
        observer.assert_not_called()
        sub._socket.send.assert_not_called()
        sub.request('printer.gcode.script', {'script':'G28 X\nG28 Y'})
        sub._drain_outbound()
        observer.assert_called_once_with('HOMING',4)
        self.assertIn('id',json.loads(sub._socket.send.call_args.args[0]))

    def test_http_homing_observer_runs_only_when_worker_admits_command(self):
        client = MoonrakerClient()
        self.addCleanup(client.close)
        sent = Event()
        client.request = Mock(return_value={'result':None})
        client.script_dispatch_callback = lambda script: sent.set()
        future = client.post('/printer/gcode/script', {'script':'G28'},guard=lambda:False)
        with self.assertRaises(MoonrakerError): future.result(1)
        self.assertFalse(sent.is_set())
        client.post('/printer/gcode/script', {'script':'G28'}).result(1)
        self.assertTrue(sent.is_set())

    def test_mesh_success_waits_for_readback_and_failure_is_server_error_only(self):
        from test_bed_mesh import MeshTests
        fixture = MeshTests()
        p, session = fixture.make()
        session.start()
        p.subscription.emit_operation_melody.assert_not_called()
        fixture.complete(session)
        p.subscription.emit_operation_melody.assert_called_once_with('PROBE_SUCCESS', session.epoch)
        session.update()
        self.assertEqual(p.subscription.emit_operation_melody.call_count,1)
        for stage, expected in [('server_error',1),('send_attempted',0),('guard_denied',0)]:
            p, session = fixture.make()
            session.start()
            session.pending.dispatch_stage = stage
            session.pending.set_exception(MoonrakerError('Probe command failed'))
            session.update()
            self.assertEqual(p.subscription.emit_operation_melody.call_count,expected)
            if expected:
                p.subscription.emit_operation_melody.assert_called_with('PROBE_FAIL',session.epoch)

    def test_manual_probe_accept_and_abort_are_distinct(self):
        from test_probe_wizard import ProbeTests
        fixture = ProbeTests()
        p = fixture.started()
        p.subscription.emit_operation_melody.assert_not_called()
        p.probe_wizard.accept().set_result('ok')
        fixture.status(p,False,{'bltouch':{'z_offset':'1.234'}})
        p.probe_wizard.update()
        p.subscription.emit_operation_melody.assert_called_once_with('PROBE_SUCCESS',p.probe_wizard.epoch)
        p = fixture.started()
        p.probe_wizard.abort().set_result('ok')
        fixture.status(p,False)
        p.probe_wizard.update()
        p.subscription.emit_operation_melody.assert_not_called()

    def test_rejected_manual_step_does_not_end_or_fail_the_session(self):
        from test_probe_wizard import ProbeTests
        p = ProbeTests().started()
        future = p.probe_wizard._submit('step', 'TESTZ Z=-0.01')
        future.dispatch_stage = 'server_error'
        future.set_exception(MoonrakerError('Step rejected'))
        p.probe_wizard.update()
        self.assertEqual(p.probe_wizard.phase, 'active')
        p.subscription.emit_operation_melody.assert_not_called()

    def test_screws_probing_completes_even_when_adjustment_is_needed(self):
        from test_screws_tilt import SessionTests, payload
        p, session = SessionTests().make()
        session.start()
        session.pending.set_result(None)
        session.update()
        p.subscription.emit_operation_melody.assert_not_called()
        session.pending.set_result(payload())
        session.update()
        self.assertFalse(session.leveled)
        p.subscription.emit_operation_melody.assert_called_once_with('PROBE_SUCCESS',session.epoch)
