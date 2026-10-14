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

def output(name,value):
    path=os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path,'a',encoding='utf-8') as handle:handle.write(name+'='+value+'\n')

def service(seconds=480):
    context()
    if type(seconds) is not int or not 60<=seconds<=1200:raise ValueError('Unsafe worker lifetime')
    key=os.environ.get('CENTRAL_SCHEDULER_KEY','')
    if not re.fullmatch(r'[a-f0-9]{64}',key):raise CredentialRejected('Scoped worker key missing')
    output('renew','true');deadline=time.monotonic()+seconds;confirmed=0;failed=0;cycles=0;last=None
    while time.monotonic()<deadline:
        start=time.monotonic();cycles+=1
        try:
            wake(key,'work');confirmed+=1;failed=0;last=time.monotonic();result='completed'
        except CredentialRejected:
            output('renew','false');raise
        except Busy:result='busy'
        except Exception:failed+=1;result='not-confirmed'
        print(json.dumps({'cycle':cycles,'result':result}),flush=True)
        delay=min(max(0,PERIOD-(time.monotonic()-start)),max(0,deadline-time.monotonic()))
        if delay:time.sleep(delay)
    maintenance='not-confirmed'
    try:
        wake(key,'maintenance');maintenance='completed'
    except CredentialRejected:
        output('renew','false');raise
    except Busy:maintenance='busy'
    except Exception:pass
    healthy=confirmed>0 and failed==0 and last is not None and time.monotonic()-last<=240 and maintenance!='not-confirmed'
    print(json.dumps({'confirmed_cycles':confirmed,'maintenance':maintenance,'healthy':healthy}),flush=True)
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as handle:
            handle.write('### Authenticated scheduler\n\nConfirmed operations: '+str(confirmed)
                         +'\n\nFinal verification: '+('passed' if healthy else 'not confirmed')
                         +'\n\nNo customer content, URLs, API responses or credentials are included.\n')
    if not healthy:raise RuntimeError('Worker did not finish with fresh confirmation')
    return True

def github(token,path,payload=None):
    if path not in ('','/actions/workflows/'+WORKFLOW,'/actions/workflows/'+WORKFLOW+'/dispatches'):
        raise ValueError('Unsupported GitHub resource')
    request=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json',
                 'User-Agent':'Avatomis-Scheduler','X-GitHub-Api-Version':'2022-11-28'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
            raw=response.read(32769)
            if len(raw)>32768:raise RuntimeError('GitHub response outside safe bounds')
            return response.status,json.loads(raw) if raw else None
    except Exception:raise RuntimeError('Scheduler handoff not confirmed') from None

def renew(delay=15):
    context();token=os.environ.get('GITHUB_TOKEN','')
    if not token or '\n' in token or '\r' in token:raise RuntimeError('Job-scoped authorization missing')
    if type(delay) is not int or not 0<=delay<=180:raise ValueError('Unsafe cooldown')
    code,repo=github(token,'')
    if code!=200 or repo.get('full_name')!=REPOSITORY or repo.get('private') is not False:
        raise RuntimeError('Continuous worker requires the original public repository')
    code,workflow=github(token,'/actions/workflows/'+WORKFLOW)
    if code!=200 or workflow.get('path')!='.github/workflows/'+WORKFLOW:raise RuntimeError('Unexpected workflow')
    if workflow.get('state')!='active':print('{"successor":"disabled"}');return False
    if delay:time.sleep(delay)
    code,_=github(token,'/actions/workflows/'+WORKFLOW+'/dispatches',{'ref':'main'})
    if code!=204:raise RuntimeError('Successor not confirmed')
    print('{"successor":"accepted"}');return True

if __name__=='__main__':
    try:
        if sys.argv[1:]==['--renew']:renew(int(os.environ.get('SCHEDULER_RENEW_DELAY','15')))
        elif not sys.argv[1:]:service(int(os.environ.get('SCHEDULER_RUN_SECONDS','480')))
        else:raise ValueError('Unsupported command')
    except Exception:
        print('Scheduler operation was not fully confirmed; no private response was logged.',file=sys.stderr);sys.exit(1)
