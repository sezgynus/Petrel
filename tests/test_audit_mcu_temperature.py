import unittest
from unittest.mock import patch
from test_capabilities import printer, snapshot, backend
from printer_state import PrinterState

class McuTemperatureIdentity(unittest.TestCase):
    def test_suffix_named_mcu_never_inherits_primary_temperature(self):
        data=snapshot()
        data['settings'].update({
            'temperature_sensor primary':{'sensor_type':'temperature_mcu'},
            'temperature_sensor secondary':{'sensor_type':'temperature_mcu','sensor_mcu':'toolhead_mcu'}})
        data['status'].update({'mcu':{},'mcu toolhead_mcu':{},'mcu unused_mcu':{},
            'temperature_sensor primary':{'temperature':42.},
            'temperature_sensor secondary':{'temperature':55.}})
        p=printer(data);p.state=PrinterState.from_snapshot(data)
        p.client.get.return_value={'result':{'version_info':{}}}
        with patch.object(backend,'network_info',return_value=('Online','1.2.3.4')), \
             patch.object(backend,'host_metrics',return_value=(10.,45.)), \
             patch.object(backend,'host_memory_usage',return_value=20.):
            p.refresh_system_info(force=True)
        values={m['name']:m['temperature'] for m in p.system_info['mcus']}
        self.assertEqual(values,{'mcu':42.,'mcu toolhead_mcu':55.,'mcu unused_mcu':None})
