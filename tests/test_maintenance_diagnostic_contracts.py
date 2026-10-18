"""CI-only coverage from real information contracts to readable LCD reports."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from test_capabilities import display,snapshot
from maintenance_evidence_view import evidence_lines
from maintenance_executor import _read_fields,read_only_adapters
from maintenance_tmc_direct import register_evidence
from maintenance_report import report_pages,section_from_lines
from maintenance_experience import LABELS

CASES={
 'H11':(('power',.42),),
 'H14':(('temperature',24.5),),
 'H16':(('humidity',48.2),('pressure',1013.2),('gas',12000)),
 'M07':(('register','DRV_STATUS'),('register_hex','C0100000'),('fault_count',0),
        ('faults','none reported'),('standstill',1),('cs_actual',16),('stealth',1)),
 'M08':(('temperature',50.2),),
 'M09':(('run_current',.8),('hold_current',.4)),
 'M11':(('stepper_x',True),('stepper_y',False),('extruder',True)),
 'M12':(('stepper_x.phase','7/64'),),
 'M13':(('angle toolhead.temperature',42.5),),
 'M14':(('homed_axes','xy'),('commanded_x',123.4),('commanded_y',45.6),('commanded_z',7.8),('max_velocity_mm_s',300)),
 'M16':(('carriage_0','PRIMARY'),('carriage_1','COPY'),('active_carriage',0)),
 'E13':(('linked_spools',2),('declared_used_mm',12345),('wear_measured',False)),
 'E15':(('humidity_pct',48.2),),
 'S01':(('cpu.cpu',36.5),('memory.available',193992)),
 'S02':(('cpu_temp_c',52.6),),
 'S03':(('throttled_bits',0),),
 'S04':(('total_bytes',31000000000),('used_bytes',11000000000),('free_bytes',20000000000)),
 'S05':(('wlan0.rx_bytes',123456),('wlan0.tx_bytes',654321)),
 'S06':(('mcu.mcu_awake',.023),('mcu.mcu_task_avg',.000145),('mcu.mcu_task_stddev',.000173),
        ('mcu mmu.mcu_task_avg',.000026)),
 'S07':(('rx_error',0),('tx_error',0),('tx_retries',2),('bus_state','error-active')),
 'S08':(('webhooks_state','ready'),('configuration_warnings',0)),
 'S09':(('buffered_events',20),('error_events',1),('last_error_code','webhook_shutdown')),
 'S10':(('total_jobs',32),('total_time',1234),('total_print_time',1200),('total_filament_used',23456)),
 'S11':(('recorded_results',2),('recent_0','H01 PASSED_USER'),('recent_1','M07 None')),
 'S12':(('coverage','sampled_lower_bound_not_lifetime'),('sampled_print_s',7384),
        ('extruder.sampled_on_s',3672),('heater_bed.sampled_on_s',1800),('fan.sampled_on_s',62)),
 'S13':(('x_mm',12345),('y_mm',54321),('z_mm',123)),
 'S14':(('uart_epoch',1),('startup_assets_synced',True),('tx_frames',1234),('tx_bytes',123456),
        ('rx_bytes',65432),('handshake_requests',2),('crc_notifications',0),
        ('response_timeouts',0),('responses',0),('aux',0)),
 'S15':(('gpio_button_presses',0),('gpio_positive_steps',42),('gpio_negative_steps',18)),
 'S16':(('startup_assets_synced',False),('uart_epoch',2)),
 'S19':(('klipper.current','v0.13.0-42-gabc123'),('klipper.available',True),
        ('moonraker.current','v0.11.0'),('moonraker.available',False)),
 'S20':(('report_ready',True),('download','maintenance-report.json'),('results',2)),
 'O05':(('ambient_c',24.2),),
}

class DiagnosticContractCoverage(unittest.TestCase):
    def readable(self,feature,evidence):
        lines=evidence_lines(feature,evidence)
        self.assertTrue(lines)
        self.assertNotIn('support report',' '.join(lines))
        self.assertNotIn('No readings available.',' '.join(lines))
        return ' '.join(lines)

    def test_every_registered_reader_has_data_and_a_real_heading(self):
        self.assertEqual(set(CASES),{r.feature_id for r in read_only_adapters()})
        for feature,evidence in CASES.items():
            with self.subTest(feature=feature):
                self.assertIn(feature,LABELS)
                shown=self.readable(feature,evidence)
                self.assertNotIn('observed_information',shown)
                d=display(snapshot());d._maintenance_init();d._maintenance_page='result'
                d._maintenance_result=NS(feature_id=feature,device=None,status=None,evidence=evidence)
                screen=d._maintenance_screen()
                self.assertNotEqual(screen.heading,'Recorded information')
                self.assertTrue(screen.sections)
                self.assertTrue(all(c.action!='none' for c in screen.choices))
                self.assertTrue(all(sum(b[2] for b in page)<=132 for page in report_pages(screen.sections)))

    def test_each_actual_diagnostic_field_is_presented_including_zero_and_false(self):
        for feature,evidence in CASES.items():
            for key,value in evidence:
                if key=='register': continue  # Its matching hex field carries the value.
                with self.subTest(feature=feature,key=key):
                    self.readable(feature,((key,value),))

    def test_direct_tmc_reply_shows_fault_meaning_and_actual_readings(self):
        evidence=register_evidence(('DRV_STATUS: C0100000',),'tmc2208 stepper_x')
        shown=self.readable('M07',evidence)
        for value in ('Driver alerts: 0','None reported','Standstill: Yes','Current scale: 16/31','Drive mode: Quiet','0xC0100000'):
            self.assertIn(value,shown)
        fault=self.readable('M07',register_evidence(('DRV_STATUS: 00000003',),'tmc2208 stepper_x'))
        self.assertIn('Temperature warning',fault);self.assertIn('Thermal shutdown',fault)
        self.assertNotIn('otpw',fault)

    def test_unknown_chip_bits_never_invent_a_clean_driver_result(self):
        for device,raw in (('tmc2208 stepper_x','00001000'),('tmc5160 stepper_x','FFFFFFFF')):
            shown=self.readable('M07',register_evidence(('DRV_STATUS: '+raw,),device))
            self.assertIn('Status register',shown)
            self.assertIn('Interpretation',shown)
            self.assertNotIn('None reported',shown)
            self.assertNotIn('Driver alerts: 0',shown)

    def test_real_mcu_parser_values_keep_time_units_and_mcu_identity(self):
        reply={'result':{'eventtime':10,'status':{
            'mcu':{'last_stats':{'mcu_awake':.023,'mcu_task_avg':.000145,'mcu_task_stddev':.000173}},
            'mcu mmu':{'last_stats':{'mcu_task_avg':.000026}}}}}
        shown=self.readable('S06',_read_fields('S06',reply))
        self.assertIn('MCU active time: 0.023 s',shown)
        self.assertIn('MCU task average: 145 us',shown)
        self.assertIn('MCU task variation: 173 us',shown)
        self.assertIn('MCU mmu task average: 26 us',shown)

    def test_real_motion_parser_does_not_call_commanded_position_measured_travel(self):
        reply={'result':{'eventtime':10,'status':{'toolhead':{
            'homed_axes':'xy','position':[12,34,56,0],'max_velocity':300}}}}
        shown=self.readable('M14',_read_fields('M14',reply))
        self.assertIn('Commanded X: 12 mm',shown)
        self.assertIn('Homed axes: X Y',shown)
        self.assertIn('Velocity limit: 300 mm/s',shown)
        self.assertNotIn('Measured travel',shown)

    def test_panel_and_encoder_local_read_results_are_not_empty_reports(self):
        d=display(snapshot())
        values=dict(CASES['S14']+CASES['S15'])
        d.pd._maintenance_panel_api=Mock(return_value=values)
        for feature in ('S14','S15','S16'):
            with self.subTest(feature=feature):
                shown=self.readable(feature,d.pd.maintenance_local_read(feature))
                self.assertNotIn('gpio_',shown)
                self.assertNotIn('startup_assets_synced',shown)
        shown=self.readable('S15',d.pd.maintenance_local_read('S15'))
        self.assertIn('Button presses: 0',shown)

    def test_saved_usage_and_history_use_real_record_reader_contracts(self):
        import maintenance_records as records
        book=NS(flush=Mock())
        with patch.object(records,'read_json',return_value={'sampled_on_s':{'fan':62,'extruder':3672},'sampled_print_s':7384}):
            usage=records.MaintenanceBook.read(book,'S12')
        shown=self.readable('S12',usage)
        self.assertIn('2h 3m 4s',shown);self.assertIn('1h 1m 12s',shown)
        self.assertIn('lower bounds',shown);self.assertNotIn('sampled_on_s',shown)
        with patch.object(records,'read_json',return_value={'records':[{'feature':'H01','status':'PASSED_USER'}]}):
            history=records.MaintenanceBook.read(book,'S11')
        shown=self.readable('S11',history)
        self.assertIn('Heater warmup',shown);self.assertIn('User observation confirmed',shown)
        self.assertNotIn('PASSED_USER',shown)

    def test_updates_identify_which_component_has_an_update(self):
        shown=self.readable('S19',CASES['S19'])
        self.assertIn('klipper update: Available',shown)
        self.assertIn('moonraker update: Not pending',shown)

    def test_usage_report_pages_keep_the_last_of_sixteen_devices(self):
        evidence=(('coverage','sampled_lower_bound_not_lifetime'),('sampled_print_s',1234))+tuple(
            ('heater_generic device%d.sampled_on_s'%i,i*1234) for i in range(16))
        sections=section_from_lines('',evidence_lines('S12',evidence))
        pages=report_pages(sections)
        self.assertGreater(len(pages),1)
        self.assertIn('device15',str(pages[-1]))
        self.assertTrue(all(sum(b[2] for b in page)<=132 for page in pages))

    def test_internal_unknown_and_invalid_values_are_not_labeled_as_measurements(self):
        shown=evidence_lines('S01',(('backend_flag',True),('unknown_distance',123),('cpu.cpu',36.5),(None,7)))
        self.assertEqual(shown,('CPU load: 36.5 %',))
        self.assertNotIn('support report',str(shown))
