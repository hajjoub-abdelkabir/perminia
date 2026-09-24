"""Private-chat HTTP/DB isolation plus provider mocks; never calls paid APIs."""
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4,UUID
from urllib.request import Request
from urllib.error import HTTPError
from sqlalchemy import create_engine,text
from sqlalchemy.engine import URL
from fastapi import HTTPException
import test_accounts as accounts
from app import chat
from app.chat_provider import ProviderFailure
from app import chat_provider

SOURCE={'id':'ref:1','title':'الأسبقية','lesson_title':'قواعد السير','slug':'priority','position':1,'status':'draft','excerpt':'محتوى تجريبي'}

class ChatPureTests(unittest.TestCase):
    def test_provider_transport_and_retry_classification(self):
        from urllib.error import HTTPError
        from unittest.mock import MagicMock
        answer=json.dumps({'answer':'شرح','source_ids':['ref:1']})
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':answer}]}],'usage':{'input_tokens':4,'output_tokens':5}}).encode()
        opener=MagicMock();opener.open.return_value=response
        with patch.object(chat_provider,'build_opener',return_value=opener):
            result,usage=chat_provider.call_provider(('openai','fake','test'),'rules',[{'role':'user','content':'الأسبقية'}])
            self.assertEqual(result,answer)
            body=json.loads(opener.open.call_args.args[0].data)
            self.assertFalse(body['store']);self.assertNotIn('tools',body)
            self.assertEqual(body['max_output_tokens'],1200)
            for code,retry in [(429,True),(503,True),(401,False),(400,False),(302,False)]:
                opener.open.side_effect=HTTPError('https://example.test',code,'sensitive upstream error',{},None)
                with self.assertRaises(ProviderFailure) as e:chat_provider.call_provider(('groq','fake','test'),'rules',[])
                self.assertEqual(e.exception.retryable,retry)
                self.assertNotIn('sensitive',str(e.exception))

    def test_sources_and_secret_output(self):
        answer,refs=chat.parse_answer(json.dumps({'answer':'شرح تجريبي','source_ids':['ref:1']}),[SOURCE])
        self.assertEqual(refs,[SOURCE])
        self.assertEqual(chat.parse_answer('{"answer":"unsupported claim","source_ids":[]}',[])[0],chat.INSUFFICIENT)
        for value in [{'answer':'invented','source_ids':['unknown']},{'answer':'sk-'+('x'*24),'source_ids':['ref:1']},{'answer':'text','source_ids':'ref:1'}]:
            with self.assertRaises(ValueError):chat.parse_answer(json.dumps(value),[SOURCE])

    def test_input_and_normalization(self):
        self.assertEqual(chat.normalize('الأَسْبَقِيَّة'),'الاسبقيه')
        for value in [' ','sk-'+('x'*24),'x'*1501]:
            with self.assertRaises(ValueError):chat.Send(request_id=uuid4(),message=value)
        with self.assertRaises(ValueError):chat.Send(request_id=uuid4(),message='سؤال',tenant_id=str(uuid4()))

    def test_memory_without_legal_citations_requires_exact_user_quote(self):
        history=[{'question':'سميت المثال السيارة الزرقاء'}]
        raw=json.dumps({'answer':'untrusted text','source_ids':[],'memory_quote':'السيارة الزرقاء'})
        answer,refs=chat.parse_answer(raw,[],history)
        self.assertIn('السيارة الزرقاء',answer);self.assertNotIn('untrusted',answer)
        self.assertEqual(chat.parse_answer(raw,[],[])[0],chat.INSUFFICIENT)

class ChatTests(accounts.AccountTests):
    @classmethod
    def setUpClass(cls):
        os.environ['CHAT_ENABLED']='false'
        super().setUpClass()
        cls.runtime=create_engine(URL.create('postgresql+psycopg',username='sya9a_student_runtime',password=os.environ['RUNTIME_DB_PASSWORD'],host=os.environ.get('POSTGRES_HOST','db'),database=cls.database),hide_parameters=True)
        cls.addClassCleanup(cls.runtime.dispose)

    def call(self,client,path='',body=None,method=None,origin=accounts.ORIGIN):
        request=Request('http://127.0.0.1:8099/api/v1/chat'+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json','Origin':origin,'X-Sya9a-Request':'student'})
        try:
            with client.opener.open(request) as r:
                self.assertEqual(r.headers['Cache-Control'],'no-store');return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)

    def test_http_scope_roles_csrf_and_disabled(self):
        first,_,u,_=self.register();other,_,v,_=self.register()
        self.assertEqual(self.call(accounts.Client(),'/threads')[0],401)
        self.assertEqual(self.call(first,'/threads',{'consent':False})[0],422)
        self.assertEqual(self.call(first,'/threads',{'consent':True},origin='https://other.test')[0],403)
        code,d=self.call(first,'/threads',{'consent':True});self.assertEqual(code,201);ident=d['id']
        self.assertEqual(self.call(other,'/threads')[1]['items'],[])
        self.assertEqual(self.call(other,'/threads/'+ident)[0],404)
        self.assertEqual(self.call(other,'/threads/'+ident,method='DELETE')[0],404)
        self.assertEqual(self.call(first,'/threads/'+ident+'/messages',{'request_id':str(uuid4()),'message':'الأسبقية'})[0],503)
        self.assertEqual(self.call(first,'/threads/'+ident+'/messages',{'bad':'x'*9000})[0],413)
        for role in ['instructor','school_manager']:
            with accounts.owner_connect(self.database) as c:c.execute('UPDATE identity.memberships SET role=%s WHERE id=%s',(role,u['membership_id']))
            self.assertEqual(self.call(first,'/threads/'+ident)[0],200)
            self.assertEqual(self.call(first,'/threads')[1]['items'][0]['id'],ident)
        self.assertEqual(self.call(first,'/threads/'+ident,method='DELETE')[0],200)
        self.assertEqual(self.call(first,'/threads/'+ident)[0],404)

    def test_memory_dedup_fallback_and_deletion_keeps_budget(self):
        client,_,user,_=self.register();ident=UUID(self.call(client,'/threads',{'consent':True})[1]['id'])
        provider=[('openai','not-a-key','test'),('groq','not-a-key','test')]
        good=(json.dumps({'answer':'هاد شرح تجريبي، تأكد مع الأستاذ.','source_ids':['ref:1']}),{'input_tokens':12,'output_tokens':15})
        with patch.object(chat,'engine',self.runtime),patch.object(chat,'providers',return_value=provider),patch.object(chat,'retrieve',return_value=[SOURCE]):
            body=chat.Send(request_id=uuid4(),message='شرح الأسبقية')
            with patch.object(chat,'call_provider',return_value=good) as generate:
                result=chat.send(ident,body,user);self.assertEqual(result['status'],'complete')
                again=chat.send(ident,body,user);self.assertEqual(again['id'],result['id']);self.assertEqual(generate.call_count,1)
                chat.send(ident,chat.Send(request_id=uuid4(),message='زيد مثال على نفس القاعدة'),user)
                messages=generate.call_args.args[2]
                self.assertEqual(messages[0]['content'],'شرح الأسبقية');self.assertEqual(messages[1]['role'],'assistant')
                self.assertNotIn(user['email'],json.dumps(messages))
            with patch.object(chat,'call_provider',side_effect=[ProviderFailure(True),good]) as generate:
                result=chat.send(ident,chat.Send(request_id=uuid4(),message='مثال آخر'),user)
                self.assertEqual(result['provider'],'groq');self.assertEqual(generate.call_count,2)
            with patch.object(chat,'call_provider',side_effect=ProviderFailure(False)) as generate:
                self.assertEqual(chat.send(ident,chat.Send(request_id=uuid4(),message='سؤال آخر'),user)['status'],'failed')
                self.assertEqual(generate.call_count,1)
            with patch.object(chat,'call_provider',return_value=('invalid JSON',{})) as generate:
                self.assertEqual(chat.send(ident,chat.Send(request_id=uuid4(),message='سؤال آخر 2'),user)['status'],'failed')
                self.assertEqual(generate.call_count,1)
            with patch.dict(os.environ,{'CHAT_USER_DAILY_LIMIT':'5'}):
                with self.assertRaises(HTTPException) as e:chat.send(ident,chat.Send(request_id=uuid4(),message='سقف'),user)
                self.assertEqual(e.exception.status_code,429)
                chat.delete(ident,user)
                new=chat.create(chat.Create(consent=True),user)['id']
                with self.assertRaises(HTTPException) as e:chat.send(new,chat.Send(request_id=uuid4(),message='سقف'),user)
                self.assertEqual(e.exception.status_code,429)

    def test_rls_same_school_and_pending_lock(self):
        client,_,user,_=self.register();other,_,other_user,_=self.register()
        ident=UUID(self.call(client,'/threads',{'consent':True})[1]['id'])
        with self.runtime.begin() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM intelligence.chat_threads')).scalar_one(),0)
            chat.scope(c,other_user)
            self.assertEqual(c.execute(text('SELECT count(*) FROM intelligence.chat_threads WHERE id=:id'),{'id':ident}).scalar_one(),0)
            chat.scope(c,{'tenant_id':user['tenant_id'],'membership_id':other_user['membership_id']})
            self.assertEqual(c.execute(text('SELECT count(*) FROM intelligence.chat_threads WHERE id=:id'),{'id':ident}).scalar_one(),0)
        with patch.object(chat,'engine',self.runtime),patch.object(chat,'providers',return_value=[('openai','fake','fake')]),patch.object(chat,'retrieve',return_value=[]):
            with self.runtime.begin() as c:
                chat.scope(c,user)
                c.execute(text("INSERT INTO intelligence.chat_turns(id,thread_id,tenant_id,membership_id,question,status) VALUES(:id,:th,:t,:m,'pending','pending')"),{'id':uuid4(),'th':ident,'t':user['tenant_id'],'m':user['membership_id']})
            with self.assertRaises(HTTPException) as e:chat.send(ident,chat.Send(request_id=uuid4(),message='جديد'),user)
            self.assertEqual(e.exception.status_code,409)
            with self.assertRaises(HTTPException) as e:chat.delete(ident,user)
            self.assertEqual(e.exception.status_code,409)

    def test_global_reservation_is_atomic_across_members(self):
        from concurrent.futures import ThreadPoolExecutor
        _,_,one,_=self.register();_,_,two,_=self.register()
        with accounts.owner_connect(self.database) as c:c.execute("DELETE FROM intelligence.chat_budget WHERE bucket='global'")
        def reserve(user):
            with self.runtime.begin() as c:
                chat.scope(c,user)
                return c.execute(text('SELECT intelligence.reserve_chat_budget(20,1)')).scalar_one()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(reserve,[one,two])),[False,True])
        with accounts.owner_connect(self.database) as c:c.execute("DELETE FROM intelligence.chat_budget WHERE bucket='global'")

if __name__=='__main__':unittest.main()
