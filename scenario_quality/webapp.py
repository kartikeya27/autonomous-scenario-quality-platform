import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .core import connect, stats, sample, resolve_issue
from .advanced import migrate, trends, meta_quality
from .security import authorize,csrf_token,verify_csrf

DB_PATH=os.environ.get('SCENARIO_DB','scenario_quality.db')

STYLE='''body{font-family:system-ui,Arial;margin:0;background:#f3f6fa;color:#17233c}header{background:#152b4d;color:white;padding:24px 6%}main{max-width:1180px;margin:26px auto;padding:0 20px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.card{background:white;padding:20px;border-radius:12px;box-shadow:0 1px 5px #d8dee8}.number{font-size:30px;font-weight:bold}table{border-collapse:collapse;background:white;width:100%;font-size:13px}td,th{padding:11px;border-bottom:1px solid #e6eaf1;text-align:left}section{margin:24px 0;overflow:auto}button{background:#235ba3;color:white;border:none;border-radius:5px;padding:6px 10px;cursor:pointer}input{padding:7px}small{color:#627188}a{color:#235ba3}'''

def render(db,csrf=""):
    migrate(db)
    x=stats(db)
    issues=db.execute('SELECT issues.*,scenarios.risk FROM issues JOIN scenarios ON scenarios.id=issues.scenario_id WHERE issues.status=? ORDER BY scenarios.risk DESC,issues.id LIMIT 30',('open',)).fetchall()
    logs=db.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT 12').fetchall()
    metrics=meta_quality(db)
    x.update({k:v for k,v in metrics.items() if k in ('first_pass_yield_pct','inspection_defect_pct','issue_rework_proxy_pct')})
    cards=''.join(f'<div class="card"><small>{html.escape(k.replace("_"," ").title())}</small><div class="number">{v}</div></div>' for k,v in x.items())
    scenario_rows=''.join(f'<tr><td>{s["id"]}</td><td>{html.escape(s["kind"])}</td><td>{s["severity"]}</td><td>{s["risk"]}</td><td>{html.escape(s["status"])}</td></tr>' for s in sample(db,25))
    issue_rows=''.join(f'<tr><td>{i["id"]}</td><td>{i["scenario_id"]}</td><td>{html.escape(i["issue_type"])}</td><td>{html.escape(i["recommendation"])}</td><td><form method="post" action="/resolve"><input type="hidden" name="id" value="{i["id"]}"><input type="hidden" name="csrf" value="{csrf}"><input name="note" required placeholder="Evidence / ticket URL"><button>Mark resolved</button></form></td></tr>' for i in issues)
    log_rows=''.join(f'<tr><td>{html.escape(l["happened_at"][:19])}</td><td>{html.escape(l["action"])}</td><td>{html.escape(l["detail"][:160])}</td></tr>' for l in logs)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scenario Quality Platform</title><style>{STYLE}</style></head><body><header><h1>Autonomous Scenario Quality Platform</h1><div>Local synthetic simulation · No real vehicle safety claims</div></header><main><div class="cards">{cards}</div><section><h2>Priority scenarios (risk-based)</h2><table><tr><th>ID</th><th>Type</th><th>Severity</th><th>Risk</th><th>Status</th></tr>{scenario_rows}</table></section><section><h2>Open maintenance work (top 30)</h2><small>Closing an issue records a review decision; it does not change underlying scenario health.</small><table><tr><th>Issue</th><th>Scenario</th><th>Problem</th><th>Suggested action</th><th>Review</th></tr>{issue_rows}</table></section><section><h2>Audit log</h2><table><tr><th>Time UTC</th><th>Action</th><th>Detail</th></tr>{log_rows}</table></section><p><a href="/api/summary">JSON Summary API</a> · <a href="/api/sample">Risk Sample API</a> · <a href="/api/issues">Open Issues API</a></p></main></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def authorized(self,permission='read'):
        return authorize(self.headers.get('Authorization',''),permission) is not None
    def do_GET(self):
        if not self.authorized():self.send_error(401);return
        with connect(DB_PATH) as db:
            migrate(db)
            path=urlparse(self.path).path
            if path=='/':
                csrf=csrf_token();data=render(db,csrf).encode();content='text/html; charset=utf-8'
            elif path=='/api/summary': data=json.dumps(stats(db)).encode(); content='application/json'
            elif path=='/api/sample': data=json.dumps(sample(db)).encode(); content='application/json'
            elif path=='/api/trends': data=json.dumps(trends(db)).encode(); content='application/json'
            elif path=='/api/meta': data=json.dumps(meta_quality(db)).encode(); content='application/json'
            elif path=='/metrics':
                x=stats(db);data=('\n'.join(f'scenario_quality_{k} {v}' for k,v in x.items() if isinstance(v,(int,float)))+'\n').encode(); content='text/plain; version=0.0.4'
            elif path=='/healthz': data=b'{"status":"ok"}'; content='application/json'
            elif path=='/api/issues': data=json.dumps([dict(x) for x in db.execute("SELECT * FROM issues WHERE status='open' ORDER BY id LIMIT 100")]).encode(); content='application/json'
            else: self.send_error(404);return
        self.send_response(200);
        if path=='/': self.send_header('Set-Cookie',f'scenario_csrf={csrf}; HttpOnly; SameSite=Strict; Path=/')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self' 'unsafe-inline'");self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        if not self.authorized('resolve'):self.send_error(403);return
        from urllib.parse import parse_qs
        if urlparse(self.path).path!='/resolve':self.send_error(404);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>8192: self.send_error(413);return
            form=parse_qs(self.rfile.read(size).decode())
            from http.cookies import SimpleCookie
            cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
            cookie=cookies['scenario_csrf'].value if 'scenario_csrf' in cookies else ''
            if not verify_csrf(cookie,form.get('csrf',[''])[0]):self.send_error(403,'Invalid CSRF token');return
            with connect(DB_PATH) as db:
                resolve_issue(db,int(form.get('id',[''])[0]),form.get('note',[''])[0])
        except (ValueError,IndexError): self.send_error(400,'Invalid issue or note');return
        self.send_response(303);self.send_header('Location','/');self.end_headers()

def serve(host='127.0.0.1',port=8000):
    if host not in ('127.0.0.1','localhost'):raise ValueError('Only loopback binding supported')
    print(f'Local dashboard: http://{host}:{port}',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
