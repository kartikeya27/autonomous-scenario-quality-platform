"""Local RBAC and CSRF protection; not an enterprise OIDC implementation."""
import hashlib,hmac,os,secrets
from http.cookies import SimpleCookie

ROLES={'viewer':frozenset({'read'}),'operator':frozenset({'read','resolve'}),'approver':frozenset({'read','resolve','approve'})}

def authorize(authorization,need='read'):
    """SCENARIO_TOKENS='token1:viewer,token2:operator' for localhost demo."""
    config=os.environ.get('SCENARIO_TOKENS','')
    legacy=os.environ.get('SCENARIO_API_TOKEN','')
    if legacy and not config:config=legacy+':approver'
    if not config:return 'anonymous-local' # restricted localhost-only demo mode
    if not authorization.startswith('Bearer '):return None
    token=authorization[7:]
    for entry in config.split(','):
        if ':' not in entry:continue
        value,role=entry.rsplit(':',1)
        if role in ROLES and hmac.compare_digest(token,value) and need in ROLES[role]:return role
    return None

def csrf_token():
    """Token applies to HTML POST forms, bound to a server-side secret."""
    value=secrets.token_hex(24)
    key=os.environ.get('SCENARIO_CSRF_KEY')
    if not key:
        # Ephemeral secret in a single process; tokens are invalid after restart.
        key=_ephemeral_secret
    signature=hmac.new(key.encode(),value.encode(),hashlib.sha256).hexdigest()
    return value+'.'+signature

_ephemeral_secret=secrets.token_hex(32)

def verify_csrf(cookie_token,form_token):
    if not cookie_token or not form_token or not hmac.compare_digest(cookie_token,form_token):return False
    try:value,sig=form_token.split('.',1)
    except ValueError:return False
    key=os.environ.get('SCENARIO_CSRF_KEY') or _ephemeral_secret
    expected=hmac.new(key.encode(),value.encode(),hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,sig)
