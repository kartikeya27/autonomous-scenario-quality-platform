"""Synthetic scenario execution, statistical inspection, and controlled maintenance."""
import json, math, random, statistics, time
from datetime import datetime, timezone
from .core import audit, evaluate

def migrate(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS executions(id INTEGER PRIMARY KEY AUTOINCREMENT, scenario_id INTEGER NOT NULL REFERENCES scenarios(id), batch TEXT NOT NULL, executed_at TEXT NOT NULL, passed INTEGER NOT NULL CHECK(passed IN(0,1)), duration_ms REAL NOT NULL, evidence TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_exec_scenario_batch ON executions(scenario_id,batch);
    CREATE TABLE IF NOT EXISTS inspections(id INTEGER PRIMARY KEY AUTOINCREMENT, batch TEXT NOT NULL, scenario_id INTEGER NOT NULL REFERENCES scenarios(id), stratum TEXT NOT NULL, defect INTEGER NOT NULL CHECK(defect IN(0,1)), inspected_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_inspections_batch ON inspections(batch);
    CREATE TABLE IF NOT EXISTS repair_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL REFERENCES issues(id), status TEXT NOT NULL CHECK(status IN('proposed','approved','verified','failed')), description TEXT NOT NULL, proposed_by TEXT NOT NULL, approved_by TEXT, verified_at TEXT, verification_execution_id INTEGER, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_repairs_issue ON repair_requests(issue_id);
    ''')
    db.commit()

def utcnow():return datetime.now(timezone.utc).isoformat()

def execute_batch(db, batch='baseline', count=None, seed_value=42, repair_scenario=None):
    """Deterministic synthetic replay, NOT a vehicle/simulator integration."""
    migrate(db)
    rows=db.execute('SELECT * FROM scenarios ORDER BY id').fetchall()
    if count is not None:rows=rows[:count]
    rng=random.Random(f'{seed_value}:{batch}')
    n=0
    for s in rows:
        # During verification synthetic remediation can fix specific modeled problems only.
        passed=(bool(s['observed_behavior']) and s['observed_behavior']==s['expected_behavior']
                and not (s['flaky'] and rng.random()<0.35)
                and rng.random()>=min(s['failures']/max(s['runs'],1),0.75))
        if repair_scenario == s['id']:passed=True
        duration=round(20+rng.random()*200,2)
        db.execute('INSERT INTO executions(scenario_id,batch,executed_at,passed,duration_ms,evidence) VALUES(?,?,?,?,?,?)',
                   (s['id'],batch,utcnow(),int(passed),duration,json.dumps({'source':'synthetic','seed':seed_value,'verification':repair_scenario==s['id']})))
        n+=1
    audit(db,'execute_batch',json.dumps({'batch':batch,'count':n,'synthetic':True}))
    db.commit()
    return n

def history(db, scenario_id):
    migrate(db)
    return [dict(x) for x in db.execute('SELECT * FROM executions WHERE scenario_id=? ORDER BY id',(scenario_id,))]

def trends(db):
    migrate(db)
    rows=db.execute('''SELECT batch,COUNT(*) executions,SUM(passed) passes,ROUND(AVG(duration_ms),2) avg_ms FROM executions GROUP BY batch ORDER BY MIN(id)''').fetchall()
    return [dict(r)|{'pass_pct':round(100*r['passes']/r['executions'],2)} for r in rows]

def wilson_interval(defects,n,z=1.96):
    if n<=0:raise ValueError('n must be positive')
    if not 0<=defects<=n:raise ValueError('defects must be in [0,n]')
    p=defects/n; denom=1+z*z/n
    center=(p+z*z/(2*n))/denom
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return (round(max(0,center-half),5),round(min(1,center+half),5))

def inspect_stratified(db,batch='inspection-1',sample_size=50,seed_value=42,acceptance_defects=0):
    """Proportional stratified SRS without replacement; descriptive Wilson 95% approximation.
    Acceptance threshold is configurable DEMO rule, not ISO 2859-1 AQL lookup.
    """
    migrate(db)
    if sample_size<=0 or acceptance_defects<0:raise ValueError('invalid sample size or acceptance threshold')
    if db.execute('SELECT 1 FROM inspections WHERE batch=? LIMIT 1',(batch,)).fetchone():raise ValueError('batch already exists')
    scenarios=[dict(x) for x in db.execute('SELECT * FROM scenarios ORDER BY id')]
    n=len(scenarios)
    if sample_size>n:raise ValueError('sample size exceeds population')
    strata={}
    for s in scenarios:strata.setdefault(s['kind'],[]).append(s)
    # Largest remainder allocation maintains requested n, including small strata.
    ideal={k:sample_size*len(v)/n for k,v in strata.items()}
    allocation={k:int(ideal[k]) for k in strata}
    for k in sorted(strata,key=lambda x:(-(ideal[x]-allocation[x]),x))[:sample_size-sum(allocation.values())]:allocation[k]+=1
    rng=random.Random(seed_value)
    selected=[]
    for kind in sorted(strata):
        for s in rng.sample(strata[kind],allocation[kind]):
            defect=int(s['status']!='healthy')
            db.execute('INSERT INTO inspections(batch,scenario_id,stratum,defect,inspected_at) VALUES(?,?,?,?,?)',(batch,s['id'],kind,defect,utcnow()))
            selected.append({'scenario_id':s['id'],'stratum':kind,'defect':defect})
    defects=sum(s['defect'] for s in selected)
    ci=wilson_interval(defects,len(selected))
    result={'batch':batch,'population':n,'sample_size':len(selected),'sampled_defects':defects,'sample_defect_rate':round(defects/len(selected),4),'wilson_95_pct_approx':ci,'allocation':allocation,'decision':'accept' if defects<=acceptance_defects else 'reject','acceptance_defects':acceptance_defects,'method':'proportional stratified random sample; pooled Wilson interval is approximate'}
    audit(db,'inspection',json.dumps(result));db.commit()
    return result

def meta_quality(db):
    migrate(db)
    inspected=db.execute('SELECT COUNT(*) n,SUM(defect) defects FROM inspections').fetchone()
    issues=db.execute('SELECT COUNT(*) n, SUM(CASE WHEN status="resolved" THEN 1 ELSE 0 END) resolved FROM issues').fetchone()
    repairs=db.execute('SELECT COUNT(*) n,SUM(CASE WHEN status="verified" THEN 1 ELSE 0 END) verified,SUM(CASE WHEN status="failed" THEN 1 ELSE 0 END) failed FROM repair_requests').fetchone()
    first=db.execute('''SELECT COUNT(*) n,SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) passed FROM executions WHERE id IN(SELECT MIN(id) FROM executions GROUP BY scenario_id)''').fetchone()
    total=first['n']; ins=inspected['n'];
    # Proxy: rework = fraction of issues with an attempted repair; not a labor/time-based rework rate.
    touched=db.execute('SELECT COUNT(DISTINCT issue_id) FROM repair_requests').fetchone()[0]
    return {'first_pass_yield_pct':round(100*(first['passed'] or 0)/total,2) if total else None,'unique_scenarios_executed':total,
            'inspection_defect_pct':round(100*(inspected['defects'] or 0)/ins,2) if ins else None,'inspections':ins,
            'issue_rework_proxy_pct':round(100*touched/issues['n'],2) if issues['n'] else None,
            'total_issues':issues['n'],'repair_attempts':repairs['n'],'verified_repairs':repairs['verified'] or 0,'failed_verifications':repairs['failed'] or 0,
            'note':'Demo metrics: first observed run per scenario; rework proxy counts issues requiring attempted repairs.'}

def propose(db,issue_id,description,actor):
    migrate(db)
    issue=db.execute('SELECT * FROM issues WHERE id=?',(issue_id,)).fetchone()
    if not issue or issue['status']!='open':raise ValueError('issue not open')
    if not description.strip() or not actor.strip():raise ValueError('description and actor required')
    cur=db.execute('INSERT INTO repair_requests(issue_id,status,description,proposed_by,created_at) VALUES(?,?,?,?,?)',(issue_id,'proposed',description,actor,utcnow()))
    audit(db,'repair_proposed',json.dumps({'repair_id':cur.lastrowid,'actor':actor}));db.commit();return cur.lastrowid

def approve(db,repair_id,actor):
    migrate(db)
    r=db.execute('SELECT * FROM repair_requests WHERE id=?',(repair_id,)).fetchone()
    if not r or r['status']!='proposed':raise ValueError('repair not awaiting approval')
    if r['proposed_by']==actor:raise ValueError('proposer cannot approve own repair')
    if not actor.strip():raise ValueError('approver required')
    db.execute("UPDATE repair_requests SET status='approved',approved_by=? WHERE id=?",(actor,repair_id))
    audit(db,'repair_approved',json.dumps({'repair_id':repair_id,'actor':actor}));db.commit()

def verify(db,repair_id,seed_value=42,simulate_success=True):
    """Controlled synthetic verification; never claims a real software patch was deployed."""
    migrate(db)
    r=db.execute('''SELECT repair_requests.*,issues.scenario_id,issues.issue_type FROM repair_requests JOIN issues ON issues.id=repair_requests.issue_id WHERE repair_requests.id=?''',(repair_id,)).fetchone()
    if not r or r['status']!='approved':raise ValueError('repair not approved')
    s=db.execute('SELECT * FROM scenarios WHERE id=?',(r['scenario_id'],)).fetchone()
    # Only synthetic 'stale' test issue is modeled as fixable by re-execution.
    supported=r['issue_type']=='stale_test'
    success=bool(simulate_success and supported)
    batch=f'verification-{repair_id}'
    if success:
        db.execute('UPDATE scenarios SET age_days=0 WHERE id=?',(s['id'],))
    # Always re-execute and record evidence, even for failed verification.
    execute_batch(db,batch=batch,count=0,seed_value=seed_value)
    db.execute('INSERT INTO executions(scenario_id,batch,executed_at,passed,duration_ms,evidence) VALUES(?,?,?,?,?,?)',
        (s['id'],batch,utcnow(),int(success),42.0,json.dumps({'source':'synthetic','issue_type':r['issue_type'],'approved_by':r['approved_by'],'verified':success})))
    execution_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
    new_status='verified' if success else 'failed'
    db.execute('UPDATE repair_requests SET status=?,verified_at=?,verification_execution_id=? WHERE id=?',(new_status,utcnow(),execution_id,repair_id))
    if success:db.execute("UPDATE issues SET status='resolved' WHERE id=?",(r['issue_id'],))
    audit(db,'repair_verified',json.dumps({'repair_id':repair_id,'passed':success,'execution_id':execution_id}))
    db.commit()
    return {'repair_id':repair_id,'status':new_status,'execution_id':execution_id,'mode':'synthetic'}
