import unittest
from types import SimpleNamespace
from maintenance_assessment_service import MaintenanceAssessment
from maintenance_heater import ThermalResult
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, AUTOMATIC, _index_for
from maintenance_heater import thermal_adapters
from maintenance_planner import build_plan
from maintenance_assessment_rules import MetricPolicy

class AssessmentBackendTest(unittest.TestCase):
    def setup_backend(self):
        now=[0.]
        state=SimpleNamespace(epoch=1,settings={})
        bits=AUTOMATIC << (_index_for('H07')*5)
        snap=MaintenanceSnapshot(1,(DeviceCapabilities('extruder','heater',bits),),
                                 config_marker=id(state.settings))
        rows=build_plan(snap,thermal_adapters())
        api=MaintenanceAssessment(clock=lambda:now[0],max_age=10)
        api.ingest(ThermalResult('H07','extruder','FAILED_METRIC','limit',True,
                   (('overshoot_c',8.),)),1,state)
        return api,snap,rows,now

    def test_stale_evidence_cannot_remain_current_health(self):
        api,snap,rows,now=self.setup_backend()
        self.assertEqual(api.report(snap,rows)[1][0].state,'attention')
        now[0]=11
        self.assertEqual(api.report(snap,rows)[1][0].state,'unknown')

    def test_policies_integrated_and_scope_filtered(self):
        api,snap,rows,now=self.setup_backend()
        p=MetricPolicy('H07','overshoot_c',upper=5,source='declared_profile')
        result=api.detailed_report(snap,rows,metric_policies=(p,))
        self.assertTrue(any(f.rule_id.startswith('metric.H07.') for f in result.findings))
        self.assertFalse(api.detailed_report(None,rows,metric_policies=(p,)).findings)

    def test_distinct_policies_cannot_erase_an_attention_finding(self):
        api,snap,rows,now=self.setup_backend()
        policies=(MetricPolicy('H07','overshoot_c',upper=5,source='strict',version=1),
                  MetricPolicy('H07','overshoot_c',upper=10,source='other',version=2))
        report=api.detailed_report(snap,rows,metric_policies=policies)
        metrics=[f for f in report.findings if f.rule_id.startswith('metric.')]
        self.assertEqual(len(metrics),2)
        self.assertEqual({f.state for f in metrics},{'clear','attention'})
        repeated=api.detailed_report(snap,rows,metric_policies=policies+policies)
        self.assertEqual(len([f for f in repeated.findings if f.rule_id.startswith('metric.')]),2)

    def test_storage_is_deferred_and_operations_allowlisted(self):
        calls=[]
        class Worker:
            def submit(self,fn,**kwargs):
                calls.append(fn)
                return 'future'
        self.assertEqual(MaintenanceAssessment.storage_request(
            Worker(),'unused.json','load'),'future')
        self.assertEqual(len(calls),1)
        with self.assertRaises(ValueError):
            MaintenanceAssessment.storage_request(Worker(),'unused.json','_save',{})

