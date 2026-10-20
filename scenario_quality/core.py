import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

TYPES = ('intersection', 'pedestrian', 'lane_change', 'unprotected_turn', 'construction')
WEATHERS = ('clear', 'rain', 'fog')

def connect(path='scenario_quality.db'):
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS scenarios (
      id INTEGER PRIMARY KEY, kind TEXT NOT NULL, weather TEXT NOT NULL,
      severity INTEGER NOT NULL, failures INTEGER NOT NULL,
      runs INTEGER NOT NULL, flaky INTEGER NOT NULL,
      age_days INTEGER NOT NULL, owner TEXT NOT NULL,
      expected_behavior TEXT NOT NULL, observed_behavior TEXT NOT NULL,
      risk REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'healthy');
    CREATE TABLE IF NOT EXISTS issues (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scenario_id INTEGER NOT NULL REFERENCES scenarios(id),
      issue_type TEXT NOT NULL, recommendation TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open',
      UNIQUE(scenario_id,issue_type));
    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT, happened_at TEXT NOT NULL,
      action TEXT NOT NULL, detail TEXT NOT NULL);
    ''')
    db.commit()
    return db

def audit(db, action, detail):
    db.execute('INSERT INTO audit_log(happened_at,action,detail) VALUES (?,?,?)',
               (datetime.now(timezone.utc).isoformat(),action,detail))

def seed(db, count=250):
    rng=random.Random(42)
    db.execute('DELETE FROM issues')
    db.execute('DELETE FROM scenarios')
    db.execute('DELETE FROM audit_log')
    for sid in range(1,count+1):
        kind=rng.choice(TYPES)
        severity=rng.randint(1,5)
        runs=rng.randint(10,150)
        failures=rng.randint(0,min(runs,30)) if sid%9==0 else rng.randint(0,min(runs,3))
        flaky=1 if sid%13==0 else 0
        age_days=rng.randint(1,110)
        expected='safe_stop' if kind in ('pedestrian','intersection') else 'safe_navigation'
        observed='' if sid%19==0 else ('unexpected_movement' if sid%11==0 else expected)
        db.execute('''INSERT INTO scenarios(id,kind,weather,severity,failures,runs,flaky,age_days,owner,expected_behavior,observed_behavior)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(sid,kind,rng.choice(WEATHERS),severity,failures,runs,flaky,age_days,f'team-{sid%5}',expected,observed))
    audit(db,'seed',f'Loaded {count} synthetic scenarios using random seed 42')
    db.commit()

def score(s):
    rate=s['failures']/max(s['runs'],1)
    return round(min(100,18*s['severity'] + 65*rate + (20 if s['flaky'] else 0)
                         + (15 if s['age_days']>60 else 0)
                         + (18 if not s['observed_behavior'] else 0)),2)

def classify(s):
    problems=[]
    if not s['observed_behavior']:
        problems.append(('missing_evidence','Collect observed behavior and review traceability'))
    elif s['observed_behavior'] != s['expected_behavior']:
        problems.append(('unexpected_behavior','Escalate for SME review; do not automatically alter expected behavior'))
    if s['runs'] and s['failures']/s['runs'] >= 0.15:
        problems.append(('high_failure_rate','Investigate failed executions and reproduce before accepting'))
    if s['flaky']:
        problems.append(('flaky_test','Inspect nondeterminism and stabilize test fixtures'))
    if s['age_days']>60:
        problems.append(('stale_test','Re-execute the scenario against current configuration'))
    return problems

def evaluate(db):
    scenarios=db.execute('SELECT * FROM scenarios ORDER BY id').fetchall()
    for s in scenarios:
        problems=classify(s)
        db.execute('UPDATE scenarios SET risk=?,status=? WHERE id=?',
                   (score(s),'unhealthy' if problems else 'healthy',s['id']))
        for kind, recommendation in problems:
            db.execute('''INSERT OR IGNORE INTO issues(scenario_id,issue_type,recommendation)
                       VALUES(?,?,?)''',(s['id'],kind,recommendation))
    audit(db,'evaluate',f'Evaluated {len(scenarios)} scenarios')
    db.commit()

def sample(db, size=20):
    if size<=0: raise ValueError('size must be positive')
    rows=db.execute('SELECT * FROM scenarios ORDER BY risk DESC,id ASC').fetchall()
    # Risk-driven audit. Not a statistically representative random or formal AQL sample.
    return [dict(s) for s in rows[:size]]

def stats(db):
    total=db.execute('SELECT count(*) AS n FROM scenarios').fetchone()['n']
    unhealthy=db.execute("SELECT count(*) AS n FROM scenarios WHERE status='unhealthy'").fetchone()['n']
    open_issues=db.execute("SELECT count(*) AS n FROM issues WHERE status='open'").fetchone()['n']
    resolved=db.execute("SELECT count(*) AS n FROM issues WHERE status='resolved'").fetchone()['n']
    return {'total':total,'healthy':total-unhealthy,'unhealthy':unhealthy,
            'health_pct':round(100*(total-unhealthy)/total,1) if total else 0,
            'open_issues':open_issues,'resolved_issues':resolved}

def resolve_issue(db, issue_id, note):
    if not note.strip(): raise ValueError('Resolution note is required')
    issue=db.execute('SELECT * FROM issues WHERE id=?',(issue_id,)).fetchone()
    if not issue: raise ValueError('Unknown issue')
    if issue['status']!='open': raise ValueError('Issue is already resolved')
    db.execute("UPDATE issues SET status='resolved' WHERE id=?",(issue_id,))
    audit(db,'resolution',json.dumps({'issue_id':issue_id,'scenario_id':issue['scenario_id'],'note':note}))
    db.commit()
    # Resolving a ticket is NOT the same as restoring scenario health.
