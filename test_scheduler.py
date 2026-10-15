"""Synthetic privacy/receipt tests; no network or real credentials."""
import unittest,json,time,hmac,hashlib,os,urllib.error
from unittest.mock import patch
import scheduler as s
KEY='a'*64
class Response:
 status=200
 def __init__(self,body):self.body=body
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,n):return self.body[:n]
class Tests(unittest.TestCase):
 def call(self,change=lambda x:x):
  def open_request(request,timeout):
   data=json.loads(request.data);seen=int(time.time())
   receipt={'ok':True,'completed':True,'seen':seen,'proof':hmac.new(KEY.encode(),f'scheduler-receipt-v1\n{data["receipt"]}\n{seen}\n1'.encode(),hashlib.sha256).hexdigest()}
   self.assertNotIn(KEY,request.full_url);self.assertEqual(set(data),{'lane','receipt'})
   return Response(json.dumps(change(receipt)).encode())
  with patch('scheduler.urllib.request.OpenerDirector.open',side_effect=open_request):return s.wake(KEY,'work')
 def test_completed(self):self.assertTrue(self.call())
 def test_invalid_receipts(self):
  for change in [lambda x:{'ok':True},lambda x:{**x,'proof':'f'*64},lambda x:{**x,'seen':0},lambda x:{**x,'customer':'private'},lambda x:{**x,'completed':False}]:
   with self.assertRaises(RuntimeError):self.call(change)
 def test_no_redirect(self):self.assertIsNone(s.NoRedirect().redirect_request(None,None,None,None,None,None))
 def test_scope(self):
  with self.assertRaises(ValueError):s.wake(KEY,'backup')
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':'someone/fork','GITHUB_REF':'refs/heads/main'}):
   with self.assertRaises(RuntimeError):s.context()
 def test_http_errors(self):
  for code,kind in [(403,s.CredentialRejected),(401,s.CredentialRejected),(429,s.Busy),(500,RuntimeError)]:
   with patch('scheduler.urllib.request.OpenerDirector.open',side_effect=urllib.error.HTTPError(s.ENDPOINT,code,'',{},None)):
    with self.assertRaises(kind):s.wake(KEY,'work')
 def test_single_batch_no_sleep_or_successor(self):
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':s.REPOSITORY,'GITHUB_REF':'refs/heads/main','CENTRAL_SCHEDULER_KEY':KEY}),patch('scheduler.wake',return_value=True)as wake,patch('scheduler.time.sleep')as sleep:
   self.assertTrue(s.once());self.assertEqual([c.args for c in wake.call_args_list],[(KEY,'work'),(KEY,'maintenance')])
   sleep.assert_not_called();self.assertFalse(hasattr(s,'renew'))
 def test_uncertain_result_not_retried(self):
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':s.REPOSITORY,'GITHUB_REF':'refs/heads/main','CENTRAL_SCHEDULER_KEY':KEY}),patch('scheduler.wake',side_effect=RuntimeError('uncertain'))as wake:
   with self.assertRaises(RuntimeError):s.once()
   self.assertEqual(wake.call_count,1)
 def test_busy_preserves_queue(self):
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':s.REPOSITORY,'GITHUB_REF':'refs/heads/main','CENTRAL_SCHEDULER_KEY':KEY}),patch('scheduler.wake',side_effect=[s.Busy(),True])as wake:
   self.assertTrue(s.once());self.assertEqual(wake.call_count,2)
if __name__=='__main__':unittest.main()
