import argparse,json,time
from .core import connect,seed,evaluate,sample,stats
from .advanced import migrate,execute_batch,trends,history,inspect_stratified,meta_quality,propose,approve,verify

from .engineering import acceptance_plan,stratified_design,replay,verify_artifact,queue_jobs,consume_jobs,benchmark as bench_jobs,setup

def main():
    p=argparse.ArgumentParser(description='Synthetic scenario quality platform')
    p.add_argument('command',choices=['init','evaluate','report','sample','serve','run','history','trends','inspect','meta','propose','approve','verify','benchmark','aql-plan','design-ci','replay','verify-artifact','queue','worker','loadtest'])
    p.add_argument('--db',default='scenario_quality.db');p.add_argument('--count',type=int,default=250);p.add_argument('--size',type=int,default=20)
    p.add_argument('--port',type=int,default=8000);p.add_argument('--batch',default='run-1');p.add_argument('--seed',type=int,default=42)
    p.add_argument('--scenario-id',type=int);p.add_argument('--issue-id',type=int);p.add_argument('--repair-id',type=int)
    p.add_argument('--n',type=int,default=40);p.add_argument('--c',type=int,default=1);p.add_argument('--aql',type=float,default=.01);p.add_argument('--lq',type=float,default=.1);p.add_argument('--artifact-id',type=int);p.add_argument('--workers',type=int,default=4);p.add_argument('--actor',default='');p.add_argument('--description',default='');p.add_argument('--acceptance-defects',type=int,default=0)
    a=p.parse_args()
    if a.command=='aql-plan':print(json.dumps(acceptance_plan(a.count,a.n,a.c,a.aql,a.lq),indent=2));return
    if a.command=='loadtest':print(json.dumps(bench_jobs(a.db,a.count,a.workers),indent=2));return
    if a.command=='worker':print(json.dumps(consume_jobs(a.db,'cli-worker',a.count),indent=2));return
    if a.command=='serve':
        from . import webapp
        webapp.DB_PATH=a.db;webapp.serve(port=a.port);return
    if a.command=='benchmark':
        if not 1<=a.count<=100000:p.error('--count must be 1..100000')
        start=time.perf_counter()
        with connect(':memory:') as db:
            seed(db,a.count);evaluate(db);result=stats(db)
        print(json.dumps({'scenarios':a.count,'elapsed_seconds':round(time.perf_counter()-start,3),'environment':'local synthetic sqlite in-memory','quality':result},indent=2));return
    with connect(a.db) as db:
        setup(db)
        if a.command=='init':
            if not 1<=a.count<=100000:p.error('--count must be 1..100000')
            db.execute('DELETE FROM repair_requests');db.execute('DELETE FROM inspections');db.execute('DELETE FROM executions');db.commit()
            seed(db,a.count);evaluate(db);print(f'Loaded and evaluated {a.count} scenarios in {a.db}')
        elif a.command=='evaluate':evaluate(db);print('Evaluation complete')
        elif a.command=='design-ci':print(json.dumps(stratified_design(db,a.n,a.seed),indent=2))
        elif a.command=='replay':
            if a.scenario_id is None:p.error('--scenario-id required')
            print(json.dumps(replay(db,a.scenario_id),indent=2))
        elif a.command=='verify-artifact':
            if a.artifact_id is None:p.error('--artifact-id required')
            print(json.dumps(verify_artifact(db,a.artifact_id),indent=2))
        elif a.command=='queue':print(json.dumps({'queued':queue_jobs(db,a.count)},indent=2))
        elif a.command=='report':print(json.dumps(stats(db),indent=2))
        elif a.command=='sample':print(json.dumps(sample(db,a.size),indent=2))
        elif a.command=='run':print(json.dumps({'executions':execute_batch(db,a.batch,seed_value=a.seed),'batch':a.batch},indent=2))
        elif a.command=='history':
            if a.scenario_id is None:p.error('--scenario-id required')
            print(json.dumps(history(db,a.scenario_id),indent=2))
        elif a.command=='trends':print(json.dumps(trends(db),indent=2))
        elif a.command=='inspect':print(json.dumps(inspect_stratified(db,a.batch,a.size,a.seed,a.acceptance_defects),indent=2))
        elif a.command=='meta':print(json.dumps(meta_quality(db),indent=2))
        elif a.command=='propose':
            if a.issue_id is None:p.error('--issue-id required')
            print(json.dumps({'repair_id':propose(db,a.issue_id,a.description,a.actor)}))
        elif a.command=='approve':
            if a.repair_id is None:p.error('--repair-id required')
            approve(db,a.repair_id,a.actor);print('Approved')
        elif a.command=='verify':
            if a.repair_id is None:p.error('--repair-id required')
            print(json.dumps(verify(db,a.repair_id),indent=2))
if __name__=='__main__':main()
