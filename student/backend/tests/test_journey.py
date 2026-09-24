"""Student dashboard isolation and goal persistence against a disposable database."""
import json
import os
from datetime import date,timedelta
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
from test_accounts import AccountTests,Client,owner_connect
from app.coach import context,generate,configured
from app.journey import aggregate
from app.coach import coach,CoachRequest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

class JourneyTests(AccountTests):
    def api(self,client,path='',body=None,method=None,origin='http://localhost:5174'):
        req=Request('http://127.0.0.1:8099/api/v1/student/journey'+path,
            data=json.dumps(body).encode() if body is not None else None,method=method,
            headers={'Origin':origin,'X-Sya9a-Request':'student','Content-Type':'application/json'})
        try:
            with client.opener.open(req,timeout=15) as r:return r.status,json.load(r),r.headers
        except HTTPError as e:return e.code,json.load(e),e.headers

    def test_empty_state_private_goals_and_isolation(self):
        a,_,u,_=self.register();b,_,v,_=self.register()
        self.assertEqual(self.api(Client())[0],401)
        code,data,headers=self.api(a)
        self.assertEqual(code,200);self.assertIsNone(data['score']);self.assertFalse(data['is_demo'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        body={'daily_minutes':30,'exam_on':(date.today()+timedelta(days=45)).isoformat()}
        for _ in range(2):self.assertEqual(self.api(a,'/goal',body,'PUT')[0],200)
        self.assertEqual(self.api(a)[1]['profile']['daily_minutes'],30)
        self.assertEqual(self.api(b)[1]['profile']['daily_minutes'],20)
        self.assertEqual(self.api(a,'/goal',{**body,'membership_id':v['membership_id']},'PUT')[0],422)
        self.assertEqual(self.api(a,'/goal',body,'PUT',origin='https://evil.example')[0],403)
        self.assertEqual(self.api(a,'/goal',{**body,'daily_minutes':0},'PUT')[0],422)
        with owner_connect(self.database) as c:
            c.execute('SET LOCAL ROLE sya9a_student_runtime')
            for table in ('learning.journey_profiles','learning.demo_performance','learning.preview_sessions','intelligence.coach_reports'):
                self.assertEqual(c.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            c.execute("SELECT set_config('app.tenant_id',%s,true),set_config('app.membership_id',%s,true)",(str(v['tenant_id']),str(u['membership_id'])))
            self.assertEqual(c.execute('SELECT count(*) FROM learning.journey_profiles').fetchone()[0],0)

    def test_coach_no_model_claim_without_provider(self):
        a,_,_,_=self.register()
        code,data,_=self.api(a,'/coach',{'intent':'analysis'})
        self.assertEqual(code,200);self.assertEqual(data['source'],'rules');self.assertEqual(data['reason'],'not_configured')
        self.assertEqual(self.api(a,'/coach',{'intent':'legal_advice'})[0],422)
        self.assertEqual(self.api(a,'/coach',{'intent':'analysis','score':100})[0],422)

    def test_weighted_metrics_and_provider_contract(self):
        self.assertIsNone(aggregate([]))
        self.assertEqual(aggregate([{'correct':1,'total':1},{'correct':0,'total':9}]),10)
        with patch.dict(os.environ,{'STUDENT_AI_ENABLED':'false','OPENAI_API_KEY':'test-only','OPENAI_MODEL':'test-model'}):
            self.assertFalse(configured())
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'راجع بشوية.'}]}],'usage':{'input_tokens':12,'output_tokens':8}}).encode()
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','OPENAI_MODEL':'test-model'}),patch('app.coach.urlopen',return_value=Reply()) as mocked:
            answer,usage=generate({'is_demo':True},'plan')
            self.assertEqual(answer,'راجع بشوية.')
            payload=json.loads(mocked.call_args.args[0].data)
            self.assertFalse(payload['store']);self.assertEqual(payload['max_output_tokens'],700)
            self.assertNotIn('tools',payload);self.assertEqual(usage['output_tokens'],8)

    def test_coach_cache_quota_and_failure_are_persistent(self):
        a,_,user,_=self.register()
        runtime=create_engine(URL.create('postgresql+psycopg',username='sya9a_student_runtime',password=os.environ['RUNTIME_DB_PASSWORD'],host=os.environ.get('POSTGRES_HOST','db'),database=self.database))
        self.addCleanup(runtime.dispose)
        with patch('app.coach.engine',runtime),patch('app.journey.engine',runtime),patch.dict(os.environ,{'STUDENT_AI_ENABLED':'true','OPENAI_MODEL':'test-model','OPENAI_API_KEY':'not-a-real-key'}),patch('app.coach.generate',return_value=('توجيه اختباري.',{'input_tokens':10,'output_tokens':5})) as provider:
            first=coach(CoachRequest(intent='analysis'),Response(),user)
            again=coach(CoachRequest(intent='analysis'),Response(),user)
            self.assertEqual(first['source'],'openai');self.assertEqual(again['reason'],'cached');self.assertEqual(provider.call_count,1)
            coach(CoachRequest(intent='plan'),Response(),user)
            provider.side_effect=TimeoutError()
            failed=coach(CoachRequest(intent='motivation'),Response(),user)
            self.assertEqual(failed['source'],'rules');self.assertEqual(failed['reason'],'failed')
            self.api(a,'/goal',{'daily_minutes':60},'PUT')
            limited=coach(CoachRequest(intent='analysis'),Response(),user)
            self.assertEqual(limited['reason'],'daily_limit');self.assertEqual(provider.call_count,3)
