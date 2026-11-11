"""Optional heaters share dispatch evidence without permanent subscriptions."""
import unittest
from concurrent.futures import Future
from petrel.moonraker.subscription import MoonrakerSubscription
from petrel.features.maintenance.domains.thermal.measurements import contract

class OptionalHeaterTelemetry(unittest.TestCase):
    def make(self):
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        sub._state, sub._epoch = 'ready', 3
        sub._objects = ['extruder', 'heater_generic chamber', 'output_pin case_light']
        sub._settings = {n: {'heater_pin':'PA1','min_temp':0.,'max_temp':280.}
                         for n in ('extruder','heater_generic chamber')}
        sub._base_subscription = {'extruder':None, 'toolhead':None}
        sub._status = {'extruder':{'temperature':25.,'target':0.,'power':0.}}
        self.calls=[]
        def request(method, params):
            future=Future(); self.calls.append((method,params,future)); return future
        sub.request=request
        return sub

    def test_explicit_lease_makes_all_heater_off_guard_queryable_then_releases(self):
        sub=self.make()
        future=sub.set_thermal_tracking(True)
        self.assertEqual(self.calls[-1][1]['objects']['heater_generic chamber'],
                         ['temperature','target','power'])
        future.set_result({'status':{'heater_generic chamber':
                          {'temperature':25.,'target':0.,'power':0.}},'eventtime':1.})
        snap=sub.snapshot()
        contract('extruder',snap['settings'],snap['status'],'H01')
        contract('heater_generic chamber',snap['settings'],snap['status'],'H01',(40.,60.))
        sub._merge({'heater_generic chamber':{'target':40.}},2.)
        with self.assertRaises(ValueError):
            contract('extruder',sub.snapshot()['settings'],sub.snapshot()['status'],'H01')
        sub.set_thermal_tracking(False)
        self.assertNotIn('heater_generic chamber',self.calls[-1][1]['objects'])
        self.assertNotIn('heater_generic chamber',sub.snapshot()['status'])
        sub._merge({'heater_generic chamber':{'target':0.}},3.)
        self.assertNotIn('heater_generic chamber',sub.snapshot()['status'])

    def test_light_subscription_changes_preserve_thermal_lease_and_newer_values(self):
        sub=self.make(); future=sub.set_thermal_tracking(True)
        sub.set_case_light_tracking(True)
        self.assertIn('heater_generic chamber',self.calls[-1][1]['objects'])
        sub._merge({'heater_generic chamber':{'temperature':26.,'target':0.,'power':0.}},2.)
        future.set_result({'status':{'heater_generic chamber':{'temperature':20.}},'eventtime':1.})
        self.assertEqual(sub.snapshot()['status']['heater_generic chamber']['temperature'],26.)
        sub.set_thermal_tracking(False)
        self.assertIn('output_pin case_light',self.calls[-1][1]['objects'])

    def test_late_enable_reply_cannot_restore_released_telemetry(self):
        sub=self.make(); future=sub.set_thermal_tracking(True)
        sub.set_thermal_tracking(False)
        future.set_result({'status':{'heater_generic chamber':{'temperature':25.}},'eventtime':1.})
        self.assertNotIn('heater_generic chamber',sub.snapshot()['status'])
