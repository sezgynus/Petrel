"""Human-readable diagnostics keep evidence without exposing backend flags."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from test_capabilities import display,snapshot
from petrel.features.maintenance.ui.evidence import evidence_lines
from petrel.features.maintenance.ui.experience import result_details

class DiagnosticPresentation(unittest.TestCase):
    def test_thermal_values_keep_units_without_internal_field_names(self):
        lines=evidence_lines('H07',(('overshoot_c',7.72),('stability_peak_to_peak_c',6.69)))
        self.assertIn('Overshoot: 7.72 C',lines)
        self.assertIn('Variation: 6.69 C',lines)
        self.assertNotIn('overshoot_c',str(lines))

    def test_raw_status_reason_and_restore_flags_never_reach_details(self):
        item=NS(feature_id='H07',status='FAILED_METRIC',reason='thermal_metric_threshold_exceeded',
                restore_verified=False,evidence=(('overshoot_c',7.72),('backend_flag',True)))
        text=' '.join(result_details(item))
        for internal in ('FAILED_METRIC','thermal_metric_threshold_exceeded','restore_verified','backend_flag'):
            self.assertNotIn(internal,text)
        self.assertIn('7.72 C',text)
        self.assertIn('Previous state not confirmed',text)
        self.assertNotIn('support report',text)

    def test_pi_bitmask_is_explained_and_does_not_claim_psu_failure(self):
        lines=evidence_lines('S03',(('throttled_bits',0x10001),))
        self.assertIn('Current warning: yes',lines)
        self.assertIn('Earlier warning: recorded',lines)
        self.assertNotIn('65537',str(lines));self.assertNotIn('24 V',str(lines))

    def test_information_read_displays_data_without_a_second_details_click(self):
        d=display(snapshot());d.checkkey=d.MaintenanceMenu;d._maintenance_init()
        d._maintenance_page='result';d._maintenance_result=NS(feature_id='S02',status=None,
            evidence=(('cpu_temp_c',52.6),),reason='observed_information')
        screen=d._maintenance_screen()
        self.assertEqual(screen.title,'Diagnostic data')
        self.assertIn('52.6 C',str(screen.sections))
        self.assertEqual(screen.kind,'report')
        self.assertTrue(all(c.action!='none' for c in screen.choices))
        self.assertEqual(screen.choices[0].action,'result_back')
        self.assertNotIn('observed_information',str(screen))

    def test_unknown_unit_or_field_is_not_guessed(self):
        lines=evidence_lines('S01',(('unverified_distance',123),('cpu.cpu',36.5)))
        self.assertNotIn('123',str(lines))
        self.assertIn('CPU load: 36.5 %',lines)

    def test_long_safe_text_is_wrapped_instead_of_clipped(self):
        from petrel.features.maintenance.ui.layout import _row
        from petrel.features.maintenance.ui.experience import Choice
        d=display(snapshot());d._maintenance_init();d._maintenance_selection=0
        d.lcd.reset_mock()
        _row(d,'fact',Choice('Previous state not confirmed','none'),1,100,52,None)
        texts=[c.args[-1] for c in d.lcd.draw_text.call_args_list]
        self.assertIn('Previous state not confirmed',' '.join(texts))

    def test_shorter_detail_view_keeps_full_instructions_reachable(self):
        d=display(snapshot());d._maintenance_init();d._maintenance_page='notice'
        lines=tuple('Instruction '+str(i) for i in range(6))
        d._maintenance_context=('Read carefully',lines)
        screen=d._maintenance_screen()
        choice=next(c for c in screen.choices if c.action=='instructions')
        self.assertIn('Instruction 5',choice.value)

if __name__=='__main__':
    unittest.main()
