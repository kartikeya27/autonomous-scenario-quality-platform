import os,tempfile,unittest
from unittest.mock import patch
from scenario_quality.core import connect,seed,evaluate
from scenario_quality.engineering import setup,acceptance_plan,stratified_design,replay,verify_artifact,queue_jobs,consume_jobs,benchmark
from scenario_quality.security import authorize,csrf_token,verify_csrf
class EngineeringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=self.tmp.name+'/local.db'
        with connect(self.path) as db:setup(db);seed(db,60);evaluate(db)
    def tearDown(self):self.tmp.cleanup()
    def test_exact_aql_risks(self):
        p=acceptance_plan(100,20,1)
        self.assertGreaterEqual(p['producer_risk_alpha'],0)
        self.assertLess(p['consumer_risk_beta'],1)
        self.assertEqual(p['oc_curve'][0]['acceptance_probability'],1)
    def test_design_ci(self):
        with connect(self.path) as db:r=stratified_design(db,30,42)
        self.assertEqual(sum(x['sample'] for x in r['strata']),30)
        self.assertTrue(0<=r['estimate']<=1)
    def test_signed_replay_tamper_detection(self):
        with connect(self.path) as db:
            r=replay(db,1,key='a-very-long-demo-signing-secret')
            self.assertTrue(verify_artifact(db,r['artifact_id'],key='a-very-long-demo-signing-secret')['valid'])
            db.execute('UPDATE replay_artifacts SET payload=? WHERE id=?',('{}',r['artifact_id']))
            self.assertFalse(verify_artifact(db,r['artifact_id'],key='a-very-long-demo-signing-secret')['valid'])
    def test_workers_claim_unique_jobs(self):
        with connect(self.path) as db:self.assertEqual(queue_jobs(db,12),12)
        a=consume_jobs(self.path,'worker-A',7);b=consume_jobs(self.path,'worker-B',7)
        self.assertEqual(a['completed']+b['completed'],12)
    def test_security(self):
        with patch.dict(os.environ,{'SCENARIO_TOKENS':'viewer-token:viewer,admin-token:approver'}):
            self.assertIsNone(authorize('Bearer viewer-token','approve'))
            self.assertEqual(authorize('Bearer admin-token','approve'),'approver')
            t=csrf_token();self.assertTrue(verify_csrf(t,t));self.assertFalse(verify_csrf(t,t+'x'))
    def test_benchmark(self):
        d=benchmark(self.path,30,3)
        self.assertEqual(d['completed'],30)
        self.assertIsNotNone(d['job_duration_ms']['p95'])
if __name__=='__main__':unittest.main()
