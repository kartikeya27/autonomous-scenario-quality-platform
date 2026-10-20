import unittest
from scenario_quality.core import connect,seed,evaluate,stats,sample,resolve_issue,score,classify

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:');seed(self.db,100);evaluate(self.db)
    def tearDown(self):self.db.close()
    def test_counts(self):
        s=stats(self.db);self.assertEqual(s['total'],100)
        self.assertEqual(s['healthy']+s['unhealthy'],100)
        self.assertGreater(s['open_issues'],0)
    def test_risk_order(self):
        ss=sample(self.db,20)
        self.assertEqual(len(ss),20)
        self.assertEqual([x['risk'] for x in ss],sorted([x['risk'] for x in ss],reverse=True))
    def test_score_bounded(self):
        for s in sample(self.db,100):self.assertGreaterEqual(score(s),0);self.assertLessEqual(score(s),100)
    def test_resolution_audited_and_no_health_change(self):
        row=self.db.execute('SELECT id,scenario_id FROM issues LIMIT 1').fetchone()
        before=self.db.execute('SELECT status FROM scenarios WHERE id=?',(row['scenario_id'],)).fetchone()['status']
        resolve_issue(self.db,row['id'],'Synthetic SME ticket DEMO-1 checked')
        after=self.db.execute('SELECT status FROM scenarios WHERE id=?',(row['scenario_id'],)).fetchone()['status']
        self.assertEqual(before,after)
        self.assertEqual(self.db.execute('SELECT status FROM issues WHERE id=?',(row['id'],)).fetchone()['status'],'resolved')
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit_log WHERE action='resolution'").fetchone()[0],1)
    def test_empty_evidence_flagged(self):
        s=dict(sample(self.db,1)[0]);s['observed_behavior']=''
        self.assertIn('missing_evidence',[x[0] for x in classify(s)])
    def test_reject_empty_note(self):
        issue=self.db.execute('SELECT id FROM issues LIMIT 1').fetchone()['id']
        with self.assertRaises(ValueError):resolve_issue(self.db,issue,' ')
if __name__=='__main__':unittest.main()
