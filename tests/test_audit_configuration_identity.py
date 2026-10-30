import unittest
import tempfile
from pathlib import Path
from dataclasses import replace
from printer_state import freeze
from configuration_identity import stable_digest, legacy_digest
from petrel.features.maintenance.assessment.model import Evidence, Measurement
from petrel.features.maintenance.assessment.store import AssessmentStore

class ConfigurationIdentity(unittest.TestCase):
    def test_frozen_nested_mappings_ignore_insertion_order_but_not_values(self):
        a=freeze({'extruder':{'max_temp':280,'pins':['a','b']},'printer':{'kinematics':'cartesian'}})
        b=freeze({'printer':{'kinematics':'cartesian'},'extruder':{'pins':['a','b'],'max_temp':280}})
        self.assertEqual(stable_digest(a),stable_digest(b))
        self.assertNotEqual(stable_digest(a),stable_digest(freeze({'extruder':{'max_temp':281}})))
        self.assertNotEqual(stable_digest(['a','b']),stable_digest(['b','a']))
        with self.assertRaises(ValueError): stable_digest({'value':float('nan')})

    def test_exact_legacy_baseline_is_usable_without_implicit_storage_write(self):
        config=freeze({'extruder':{'max_temp':280}})
        conditions=(('profile_version',1),('target_c',60.),('initial_band','20..25 C'),
                    ('fan_state','off'),('hardware_revision','confirmed'),('duration_s',120.),
                    ('firmware_version','v1'))
        old=Evidence('H05','extruder','sensor','PASSED_USER',1.,
            (Measurement('heating_c_per_s',1.,'C/s'),),conditions,'run',legacy_digest(config),True)
        current=replace(old,config_digest=stable_digest(config))
        with tempfile.TemporaryDirectory() as folder:
            store=AssessmentStore(Path(folder)/'assessment.json')
            store.set_baseline('heater',old,confirmed=True)
            before=store.path.read_bytes()
            self.assertIsNone(store.baseline('heater',current))
            self.assertIsNotNone(store.baseline('heater',current,legacy_digest=legacy_digest(config)))
            self.assertEqual(store.path.read_bytes(),before)
            self.assertIsNone(store.baseline('heater',current,legacy_digest='different'))
