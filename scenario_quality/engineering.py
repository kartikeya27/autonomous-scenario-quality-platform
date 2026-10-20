"""Local-first engineering extensions: explicit synthetic-only boundaries."""
import concurrent.futures, hashlib, hmac, json, math, os, platform, random, sqlite3, statistics, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from .core import audit
from .advanced import migrate, utcnow

def setup(db):
    migrate(db)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS replay_artifacts(id INTEGER PRIMARY KEY,scenario_id INTEGER NOT NULL REFERENCES scenarios(id),runner TEXT NOT NULL,runner_version TEXT NOT NULL,git_revision TEXT NOT NULL,python_version TEXT NOT NULL,config_sha256 TEXT NOT NULL,payload TEXT NOT NULL,signature TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,scenario_id INTEGER NOT NULL REFERENCES scenarios(id),state TEXT NOT NULL DEFAULT 'queued',worker TEXT,attempts INTEGER NOT NULL DEFAULT 0,started_at TEXT,finished_at TEXT,result TEXT);
    CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state,id);
    CREATE TABLE IF NOT EXISTS repair_patches(repair_id INTEGER PRIMARY KEY REFERENCES repair_requests(id), patch_path TEXT NOT NULL,sha256 TEXT NOT NULL);
    ''')
    db.commit()

def hypergeom_accept_probability(N,D,n,c):
    """Chance of accepting a lot with D actual defectives, sampling n without replacement."""
    return sum(math.comb(D,k)*math.comb(N-D,n-k)/math.comb(N,n) for k in range(max(0,n-(N-D)),min(c,n,D)+1))

def acceptance_plan(N,n,c,aql=0.01,lq=0.10):
    """Exact finite-lot OC curve; NOT ISO 2859 lookup/certification."""
    if not (0<n<=N<=100000 and 0<=c<=n and 0<aql<lq<1):raise ValueError('invalid plan parameters')
    p_aql=hypergeom_accept_probability(N,round(N*aql),n,c)
    p_lq=hypergeom_accept_probability(N,round(N*lq),n,c)
    return {'lot_size':N,'sample_size':n,'acceptance_number':c,'rejection_number':c+1,'target_aql':aql,'limiting_quality':lq,'producer_risk_alpha':round(1-p_aql,6),'consumer_risk_beta':round(p_lq,6),'oc_curve':[{'defect_fraction':p,'acceptance_probability':round(hypergeom_accept_probability(N,round(N*p),n,c),6)} for p in (0,0.005,0.01,0.02,0.05,0.10,0.15,0.20)],'standard':'Custom exact hypergeometric single-sampling plan; NOT an ISO 2859-1 lookup'}

def stratified_design(db,n=40,seed=42):
    """Finite-population stratified SRS with Neyman-like equal-cost allocation and design variance."""
    data=[dict(r) for r in db.execute('SELECT kind,status FROM scenarios ORDER BY id')]
    if not data or not 1<=n<=len(data):raise ValueError('sample size outside population')
    strata={}
    for r in data:strata.setdefault(r['kind'],[]).append(int(r['status']!='healthy'))
    # Proportional allocation with minimum one observation per stratum, when possible.
    N=len(data); groups=sorted(strata)
    if n<len(groups):raise ValueError('sample must cover all strata')
    allocation={k:1 for k in groups}
    for _ in range(n-len(groups)):
        choices=[k for k in groups if allocation[k]<len(strata[k])]
        k=max(choices,key=lambda x:len(strata[x])*n/N-allocation[x]);allocation[k]+=1
    rng=random.Random(seed); estimate=0; variance=0; records=[]
    for k in groups:
        vals=strata[k]; Nh=len(vals); nh=allocation[k]; selected=rng.sample(vals,nh)
        ph=statistics.mean(selected);weight=Nh/N;estimate+=weight*ph
        sh2=statistics.variance(selected) if nh>1 else 0
        variance+=weight**2*(1-nh/Nh)*sh2/nh
        records.append({'stratum':k,'population':Nh,'sample':nh,'weight':round(weight,6),'defects':sum(selected),'rate':round(ph,6)})
    se=math.sqrt(variance);low=max(0,estimate-1.96*se);high=min(1,estimate+1.96*se)
    # Kish equivalent sample size from unequal final expansion weights; indicative only.
    weights=[len(strata[k])/allocation[k] for k in groups for _ in range(allocation[k])]
    n_eff=sum(weights)**2/sum(x*x for x in weights)
    return {'population':N,'sample_size':n,'estimate':round(estimate,6),'ci_95_normal_approx':[round(low,6),round(high,6)],'standard_error':round(se,6),'effective_n_weights':round(n_eff,2),'weight_design_effect':round(n/n_eff,5),'strata':records,'limits':'Approximate normal CI; within-stratum SRS, finite population correction; n=1 strata have unestimable variance and must be avoided for rigorous inference'}

def _canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':')).encode()
def sign_artifact(payload,key):return hmac.new(key.encode(),_canonical(payload),hashlib.sha256).hexdigest()

def _runner(s,config):
    """Isolated local replay adapter: computes outcome from input, never forces pass."""
    outcome=s['observed_behavior'] == s['expected_behavior'] and bool(s['observed_behavior'])
    if config.get('repair_stale') and s['age_days']>60: outcome=outcome and True
    return {'passed':bool(outcome),'expected':s['expected_behavior'],'observed':s['observed_behavior'],'scenario_id':s['id'],'runner':'synthetic-rule-replay-v1'}

def replay(db,scenario_id,key=None,config=None):
    setup(db)
    key=key or os.environ.get('SCENARIO_SIGNING_KEY')
    if not key or len(key)<16:raise ValueError('set SCENARIO_SIGNING_KEY (at least 16 characters)')
    s=db.execute('SELECT * FROM scenarios WHERE id=?',(scenario_id,)).fetchone()
    if s is None:raise ValueError('unknown scenario')
    cfg=config or {};result=_runner(dict(s),cfg)
    context={'runner':'synthetic-rule-replay','runner_version':'1.0','git_revision':os.environ.get('GIT_REVISION','local-unversioned'),'python_version':platform.python_version(),'config_sha256':hashlib.sha256(_canonical(cfg)).hexdigest(),'result':result,'scenario_snapshot':dict(s)}
    sig=sign_artifact(context,key)
    cur=db.execute('INSERT INTO replay_artifacts(scenario_id,runner,runner_version,git_revision,python_version,config_sha256,payload,signature,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(scenario_id,context['runner'],context['runner_version'],context['git_revision'],context['python_version'],context['config_sha256'],json.dumps(context,sort_keys=True),sig,utcnow()))
    audit(db,'signed_replay',json.dumps({'scenario_id':scenario_id,'artifact_id':cur.lastrowid,'passed':result['passed']}));db.commit()
    return {'artifact_id':cur.lastrowid,'passed':result['passed'],'signature':sig,'source':'local synthetic replay'}

def verify_artifact(db,artifact_id,key=None):
    key=key or os.environ.get('SCENARIO_SIGNING_KEY')
    if not key:raise ValueError('signing key required')
    row=db.execute('SELECT * FROM replay_artifacts WHERE id=?',(artifact_id,)).fetchone()
    if not row:raise ValueError('artifact not found')
    return {'artifact_id':artifact_id,'valid':hmac.compare_digest(row['signature'],sign_artifact(json.loads(row['payload']),key))}

def queue_jobs(db,count=100):
    setup(db)
    ids=[r[0] for r in db.execute('SELECT id FROM scenarios ORDER BY id LIMIT ?',(count,))]
    db.executemany('INSERT INTO jobs(scenario_id) VALUES(?)',[(i,) for i in ids]);db.commit();return len(ids)

def consume_jobs(path,worker='worker-1',max_jobs=100):
    """Safe SQLite claim transaction; workers may run as separate processes."""
    done=0
    for _ in range(max_jobs):
        db=sqlite3.connect(path,timeout=15,isolation_level=None)
        db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT id,scenario_id FROM jobs WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
            if row is None:db.execute('COMMIT');break
            db.execute("UPDATE jobs SET state='running',worker=?,started_at=?,attempts=attempts+1 WHERE id=?",(worker,utcnow(),row['id']))
            db.execute('COMMIT')
            scenario=db.execute('SELECT * FROM scenarios WHERE id=?',(row['scenario_id'],)).fetchone()
            result=_runner(dict(scenario),{})
            db.execute('UPDATE jobs SET state=?,finished_at=?,result=? WHERE id=?',('completed',utcnow(),json.dumps(result),row['id']))
            done+=1
        finally:db.close()
    return {'worker':worker,'completed':done}

def benchmark(path,count=300,concurrency=4):
    """Measures bounded local SQLite job consumption; includes hardware/software metadata."""
    if not 1<=count<=100000 or not 1<=concurrency<=16:raise ValueError('invalid benchmark parameters')
    from .core import connect,seed,evaluate
    with connect(path) as db:
        setup(db)
        seed(db,count);evaluate(db);queue_jobs(db,count)
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures=[pool.submit(consume_jobs,path,f'worker-{i}',count) for i in range(concurrency)]
        outcomes=[f.result() for f in futures]
    seconds=time.perf_counter()-start
    with connect(path) as db:
        counts=dict(db.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state').fetchall())
        # Execution durations are not stored per job; measure per-job timestamps as coarse wall-clock latency.
        jobs=db.execute('SELECT started_at,finished_at FROM jobs WHERE finished_at IS NOT NULL').fetchall()
    latencies=[(datetime.fromisoformat(r[1])-datetime.fromisoformat(r[0])).total_seconds()*1000 for r in jobs]
    latencies.sort()
    def percentile(p):return round(latencies[max(0,math.ceil(len(latencies)*p)-1)],3) if latencies else None
    return {'scenario_jobs':count,'workers':concurrency,'completed':counts.get('completed',0),'elapsed_seconds':round(seconds,3),'throughput_jobs_per_second':round(count/seconds,2),'job_duration_ms':{'p50':percentile(.5),'p95':percentile(.95),'p99':percentile(.99)},'system':{'python':platform.python_version(),'os':platform.platform(),'cpu_count':os.cpu_count(),'sqlite':sqlite3.sqlite_version},'limits':'Local SQLite + threads, synthetic rule runner; timestamp-derived durations include scheduling/DB contention; not calibrated AV performance'}
