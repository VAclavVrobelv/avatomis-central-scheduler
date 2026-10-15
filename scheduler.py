"""Minimal authenticated deployment trigger: no FTP, customer data, artifacts or personal token."""
import hashlib,hmac,json,os,re,secrets,sys,time,urllib.request,urllib.error

REPOSITORY='VAclavVrobelv/avatomis-central-scheduler'
WORKFLOW='scheduler.yml'
ENDPOINT='https://seo.avatomis.com/index.php?avsc=schedule'
PERIOD=75

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
class CredentialRejected(RuntimeError):pass
class Busy(RuntimeError):pass

def context():
    if os.environ.get('GITHUB_REPOSITORY')!=REPOSITORY or os.environ.get('GITHUB_REF')!='refs/heads/main':
        raise RuntimeError('Only the original main repository may run this scheduler')

def wake(key,lane):
    if not re.fullmatch(r'[a-f0-9]{64}',key) or lane not in ('work','maintenance'):
        raise ValueError('Unsupported worker request')
    nonce=secrets.token_hex(16);started=time.time()
    request=urllib.request.Request(ENDPOINT,data=json.dumps({'lane':lane,'receipt':nonce}).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=180) as response:
            raw=response.read(1025)
            if response.status!=200 or len(raw)>1024:raise RuntimeError('Completion not confirmed')
            receipt=json.loads(raw)
    except urllib.error.HTTPError as error:
        if error.code in (401,403):raise CredentialRejected('Worker key was rejected') from None
        if error.code==429:raise Busy('Another bounded worker is active') from None
        raise RuntimeError('Completion not confirmed') from None
    except Exception:
        raise RuntimeError('Completion not confirmed') from None
    if not isinstance(receipt,dict) or set(receipt)!=set(('ok','completed','seen','proof')):
        raise RuntimeError('Unexpected completion receipt')
    seen=receipt['seen'];proof=receipt['proof']
    if receipt['ok'] is not True or receipt['completed'] is not True or type(seen) is not int or not started-15<=seen<=time.time()+300:
        raise RuntimeError('No fresh completed operation')
    expected=hmac.new(key.encode(),f'scheduler-receipt-v1\n{nonce}\n{seen}\n1'.encode(),hashlib.sha256).hexdigest()
    if not isinstance(proof,str) or not hmac.compare_digest(proof,expected):raise RuntimeError('Completion proof rejected')
    # No server response or signature is copied into public logs.
    return True

def once():
    """One bounded batch per scheduled event: no polling, sleeps or self-dispatch."""
    context()
    key=os.environ.get('CENTRAL_SCHEDULER_KEY','')
    if not re.fullmatch(r'[a-f0-9]{64}',key):raise CredentialRejected('Scoped worker key missing')
    results={}
    for lane in ('work','maintenance'):
        try:
            wake(key,lane);results[lane]='completed'
        except Busy:results[lane]='busy'
    print(json.dumps({'scheduler':results,'mode':'economy'}),flush=True)
    return True

if __name__=='__main__':
    try:
        if sys.argv[1:]:raise ValueError('Unsupported command')
        once()
    except Exception:
        print('Scheduler operation was not fully confirmed; no private response was logged.',file=sys.stderr);sys.exit(1)
