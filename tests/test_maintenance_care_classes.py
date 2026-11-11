import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
from petrel.features.maintenance.records.care import family,tasks,task_label,inventory
from petrel.features.maintenance.assessment.store import ServicePolicy
from petrel.features.maintenance.records.ui_requests import request
from test_maintenance_ui_services import DeferredWorker
from test_capabilities import display,snapshot
from petrel.features.maintenance.ui.experience import Choice


class CareClassTests(unittest.TestCase):
    def test_classes_follow_object_types_never_custom_names(self):
        cases={'stepper_x':('mechanical',),'manual_stepper lift':('mechanical',),
            'extruder':('filament_feed','nozzle','heating'),'extruder1':('filament_feed','nozzle','heating'),
            'heater_bed':('heating',),'fan':('fan',),'temperature_fan case':('fan',),
            'output_pin fan':('connected_device',),'pwm_cycle_time buzzer':('connected_device',),
            'neopixel case':('lighting',),'servo latch':('actuator',),
            'filament_motion_sensor feed':('sensor',),'probe':('sensor',),
            'temperature_sensor ambient':('sensor',),'endstop stepper_z':('sensor',),
            'tmc2209 stepper_x':('electronics',),'unknown':('general',)}
        for device,expected in cases.items():
            with self.subTest(device=device): self.assertEqual(tasks(device),expected)

    def test_inventory_includes_config_only_sensors_without_test_permission(self):
        config={'bltouch':{'sensor_pin':'PA1'},'servo gate':{'pin':'PA2'},
                'stepper_x':{'endstop_pin':'^PA3'},'stepper_y':{'endstop_pin':'tmc2209_stepper_y:virtual_endstop'},
                'gcode_button door':{'pin':'PA4'},'temperature_sensor chamber':{'sensor_type':'BME280'},
                'filament_switch_sensor feed':{'switch_pin':'PA5'}}
        devices,omitted=inventory(('probe',),config)
        for name in ('probe','servo gate','endstop stepper_x','gcode_button door',
                     'temperature_sensor chamber','filament_switch_sensor feed'):
            self.assertIn(name,devices)
        self.assertNotIn('endstop stepper_y',devices)
        self.assertNotIn('bltouch',devices)
        self.assertEqual(omitted,0)
        devices,omitted=inventory(tuple('temperature_sensor s%d'%i for i in range(300)),{})
        self.assertEqual(len(devices),256);self.assertEqual(omitted,44)

    def test_single_class_skips_choice_and_back_returns_to_devices(self):
        view=display(snapshot());view._maintenance_init();view._maintenance_page='service_devices'
        view._maintenance_options=lambda:((),())
        view._maintenance_dispatch(Choice('X axis','service_device','stepper_x'))
        self.assertEqual(view._maintenance_page,'service_basis')
        self.assertEqual(view._maintenance_context,('stepper_x','mechanical'))
        self.assertIn('Mechanical maintenance',str(view._maintenance_screen()))
        view._maintenance_dispatch(Choice('Back','back'))
        self.assertEqual(view._maintenance_page,'service_devices')
        view._maintenance_dispatch(Choice('Hotend','service_device','extruder'))
        self.assertEqual(view._maintenance_page,'service_kind')
        self.assertEqual([c.value[1] for c in view._maintenance_screen().choices[1:]],
                         ['filament_feed','nozzle','heating'])

    def test_probe_endstop_and_filament_sensor_can_create_calendar_reminders(self):
        raw=snapshot(probe=True)
        raw['settings']['stepper_x']={'endstop_pin':'^PA3'}
        raw['settings']['filament_switch_sensor feed']={'switch_pin':'PA5'}
        raw['objects'].append('filament_switch_sensor feed')
        view=display(raw);view._maintenance_init();view._maintenance_page='service_devices'
        view._maintenance_options=lambda:((),())
        devices=view.pd.maintenance_service_devices()
        for device in ('probe','endstop stepper_x','filament_switch_sensor feed'):
            with self.subTest(device=device):
                self.assertIn(device,devices)
                view._maintenance_page='service_devices'
                self.assertTrue(any(c.value==device for c in view._maintenance_screen().choices))
                view._maintenance_dispatch(Choice('Sensor','service_device',device))
                self.assertEqual(view._maintenance_context,(device,'sensor'))
                view._maintenance_dispatch(Choice('Calendar','service_basis',(device,'sensor','calendar_s')))
                view._maintenance_dispatch(Choice('Review','service_review'))
                policy=view._maintenance_context
                self.assertEqual(policy.task_id,'sensor')
                with tempfile.TemporaryDirectory() as folder,patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
                    worker=DeferredWorker()
                    future=request(worker,'save_policy',policy=policy,devices=devices)
                    worker.run();self.assertEqual(future.result()[0][0][0],policy)

    def test_legacy_task_labels_change_without_merging_policies_or_resetting_anchors(self):
        self.assertEqual(task_label('inspect_clean','stepper_x'),'Mechanical maintenance')
        self.assertEqual(task_label('inspect_clean','output_pin pump'),'Connected device maintenance')
        with tempfile.TemporaryDirectory() as folder,patch('petrel.features.maintenance.records.ui_requests.Path.home',return_value=Path(folder)):
            from petrel.features.maintenance.assessment.store import AssessmentStore
            store=AssessmentStore(Path(folder)/'.config/Petrel/maintenance-assessment.json')
            policies=[ServicePolicy(task,'stepper_x','calendar_s',100,'user') for task in ('inspect_clean','lubricate')]
            for p in policies:
                store.set_service_policy(p);store.begin_tracking(p,timestamp=10)
            before=store.path.read_bytes()
            worker=DeferredWorker();f=request(worker,'load',devices=('stepper_x',));worker.run()
            self.assertEqual(len(f.result()[0]),2)
            self.assertEqual(store.path.read_bytes(),before)
