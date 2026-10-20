import unittest
from scenario_quality.core import connect,seed,evaluate
from scenario_quality.advanced import migrate,execute_batch,history,trends,inspect_stratified,wilson_interval,meta_quality,propose,approve,verify
class AdvancedTests(unittest.TestCase):
 def setUp(self):
  self.db=connect(':memory:');migrate(self.db);seed(self.db,100);evaluate(self.db)
 def tearDown(self):self.db.close()
 def test_history_and_trends(self):
  self.assertEqual(execute_batch(self.db,'a'),100);self.assertEqual(execute_batch(self.db,'b'),100)
  self.assertEqual(len(history(self.db,1)),2);self.assertEqual(len(trends(self.db)),2)
  self.assertIsNotNone(meta_quality(self.db)['first_pass_yield_pct'])
 def test_stratified_sampling_reproducible(self):
  x=inspect_stratified(self.db,'a',25,7,2);y=inspect_stratified(self.db,'b',25,7,2)
  self.assertEqual(x['sample_size'],25);self.assertEqual(x['sampled_defects'],y['sampled_defects']);self.assertEqual(sum(x['allocation'].values()),25)
  self.assertEqual(len(set(r[0] for r in self.db.execute("SELECT scenario_id FROM inspections WHERE batch='a'"))),25)
 def test_sampling_limits(self):
  with self.assertRaises(ValueError):inspect_stratified(self.db,'bad',101)
  with self.assertRaises(ValueError):wilson_interval(3,2)
 def test_repair_requires_independent_approval(self):
  issue=self.db.execute("SELECT id FROM issues WHERE issue_type='stale_test' ORDER BY id LIMIT 1").fetchone()[0]
  rid=propose(self.db,issue,'Re-execute stale test','alice')
  with self.assertRaises(ValueError):approve(self.db,rid,'alice')
  with self.assertRaises(ValueError):verify(self.db,rid)
  approve(self.db,rid,'bob');result=verify(self.db,rid)
  self.assertEqual(result['status'],'verified')
  self.assertEqual(self.db.execute('SELECT status FROM issues WHERE id=?',(issue,)).fetchone()[0],'resolved')
  self.assertEqual(len(history(self.db,self.db.execute('SELECT scenario_id FROM issues WHERE id=?',(issue,)).fetchone()[0])),1)
 def test_nonrepairable_issue_fails_verification(self):
  issue=self.db.execute("SELECT id FROM issues WHERE issue_type='missing_evidence' LIMIT 1").fetchone()[0]
  rid=propose(self.db,issue,'Unverifiable proposal','alice');approve(self.db,rid,'bob')
  self.assertEqual(verify(self.db,rid)['status'],'failed')
  self.assertEqual(self.db.execute('SELECT status FROM issues WHERE id=?',(issue,)).fetchone()[0],'open')
if __name__=='__main__':unittest.main()
