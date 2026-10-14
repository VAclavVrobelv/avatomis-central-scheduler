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
 def test_private_repository_cannot_renew(self):
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':s.REPOSITORY,'GITHUB_REF':'refs/heads/main','GITHUB_TOKEN':'synthetic'}),patch('scheduler.github',return_value=(200,{'full_name':s.REPOSITORY,'private':True})):
   with self.assertRaises(RuntimeError):s.renew(0)
 def test_successor(self):
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':s.REPOSITORY,'GITHUB_REF':'refs/heads/main','GITHUB_TOKEN':'synthetic'}),patch('scheduler.github',side_effect=[(200,{'full_name':s.REPOSITORY,'private':False}),(200,{'path':'.github/workflows/scheduler.yml','state':'active'}),(204,None)]):self.assertTrue(s.renew(0))
if __name__=='__main__':unittest.main()
