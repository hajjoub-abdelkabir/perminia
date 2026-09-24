import unittest
import json
import os
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request
from urllib.error import HTTPError
from sqlalchemy import create_engine,text
from sqlalchemy.engine import URL
from fastapi import Response,HTTPException
from test_accounts import AccountTests,owner_connect,Client
from training_fixture import install
from app import training as t
from app.mastery import summarize,select_practice

class TrainingTests(AccountTests):
    @classmethod
    def setUpClass(cls):
        os.environ['STUDENT_PREVIEW_ENABLED']='true'
        super().setUpClass()
        with owner_connect(cls.database) as c:cls.fixture=install(c)
        cls.runtime=create_engine(URL.create('postgresql+psycopg',username='sya9a_student_runtime',password=os.environ['RUNTIME_DB_PASSWORD'],host=os.environ.get('POSTGRES_HOST','db'),database=cls.database))
        cls.addClassCleanup(cls.runtime.dispose)
    def setUp(self):
        self.engine_patch=patch.object(t,'engine',self.runtime);self.engine_patch.start();self.addCleanup(self.engine_patch.stop)
        self.now=datetime.now(timezone.utc)
        self.time_patch=patch.object(t,'clock',side_effect=lambda c:self.now);self.time_patch.start();self.addCleanup(self.time_patch.stop)
    def begin(self,user,request=None,mode='preview'):
        return t.start(t.Start(request_id=request or uuid4(),series_id=self.fixture['series'] if mode=='preview' else None,mode=mode),Response(),user)
    def test_resume_submission_scoring_and_scope(self):
        _,_,u,_=self.register();_,_,v,_=self.register();request=uuid4()
        run=self.begin(u,request);item=run['current']
        self.assertEqual(self.begin(u,request)['id'],run['id'])
        self.assertNotIn('outcome',run['answers'][0]);self.assertEqual(run['review'],[])
        saved=t.selection(run['id'],t.Selection(item_id=item['id'],expected_version=0,choices=[self.fixture['keys'][0]]),Response(),u)
        self.assertEqual(saved['current']['draft_choices'],[self.fixture['keys'][0]])
        self.assertEqual(t.resume(run['id'],Response(),u)['current']['deadline'],item['deadline'])
        with self.assertRaises(HTTPException) as denied:t.resume(run['id'],Response(),v)
        self.assertEqual(denied.exception.status_code,404)
        command=t.Answer(item_id=item['id'],action='confirm',expected_version=1)
        d=t.answer(run['id'],command,Response(),u)
        self.assertEqual(t.answer(run['id'],command,Response(),u)['current']['id'],d['current']['id'])
        self.assertNotIn('outcome',d['answers'][0])
        while d['current']:d=t.answer(run['id'],t.Answer(item_id=d['current']['id'],action='skip'),Response(),u)
        self.assertEqual(d['state'],'completed');self.assertEqual(d['score'],1);self.assertEqual(d['graded_count'],7)
        self.assertFalse(d['score_complete']);self.assertIsNone(d['review'][-1]['outcome']);self.assertIsNone(d['review'][-1]['feedback'])
        self.assertEqual(d['review'][0]['feedback']['correct_choices'],[self.fixture['keys'][0]])
    def test_deadline_offline_catchup_and_late_answer(self):
        _,_,u,_=self.register();d=self.begin(u);first=d['current']
        self.now+=timedelta(seconds=31)
        late=t.selection(d['id'],t.Selection(item_id=first['id'],expected_version=0,choices=[self.fixture['keys'][0]]),Response(),u)
        self.assertEqual(late['answers'][0]['status'],'expired');self.assertEqual(late['current']['position'],2)
        self.assertEqual(late['current']['deadline'],first['deadline']+timedelta(seconds=30))
        self.now+=timedelta(minutes=5)
        done=t.resume(d['id'],Response(),u)
        self.assertEqual(done['state'],'completed');self.assertTrue(all(a['status']=='expired' for a in done['answers']))
    def test_selection_conflict_and_choice_validation(self):
        _,_,u,_=self.register();d=self.begin(u);i=d['current'];key=self.fixture['keys'][0]
        cmd=t.Selection(item_id=i['id'],expected_version=0,choices=[key])
        t.selection(d['id'],cmd,Response(),u);t.selection(d['id'],cmd,Response(),u)
        with self.assertRaises(HTTPException) as conflict:t.selection(d['id'],t.Selection(item_id=i['id'],expected_version=0,choices=[]),Response(),u)
        self.assertEqual(conflict.exception.status_code,409)
        with self.assertRaises(HTTPException):t.selection(d['id'],t.Selection(item_id=i['id'],expected_version=1,choices=[self.fixture['keys'][1]]),Response(),u)
        t.abandon(d['id'],Response(),u)
        self.assertEqual(t.resume(d['id'],Response(),u)['state'],'abandoned')
    def test_adaptive_unique_families_and_empty_mastery(self):
        _,_,u,_=self.register();d=self.begin(u,mode='adaptive');families=[]
        while d['current']:
            families.append(d['current']['question']['family_id'])
            d=t.answer(d['id'],t.Answer(item_id=d['current']['id'],action='skip'),Response(),u)
        self.assertEqual(len(families),6);self.assertEqual(len(set(families)),6)
        self.assertTrue(d['score_complete']);self.assertEqual(d['score'],0)
        self.assertEqual(t.listing(Response(),u)['mastery'],[])
    def test_http_auth_and_request_scope(self):
        client,_,_,_=self.register()
        def call(client,body=None,origin='http://localhost:5174'):
            req=Request('http://127.0.0.1:8099/api/v1/student/training',data=None if body is None else json.dumps(body).encode(),headers={'Origin':origin,'Content-Type':'application/json','X-Sya9a-Request':'student'})
            try:
                with client.opener.open(req) as r:return r.status,json.load(r)
            except HTTPError as e:return e.code,json.load(e)
        self.assertEqual(call(Client())[0],401)
        body={'request_id':str(uuid4()),'mode':'preview','series_id':str(self.fixture['series'])}
        self.assertEqual(call(client,body,'https://evil.test')[0],403)
        self.assertEqual(call(client,{**body,'membership_id':str(uuid4())})[0],422)
        self.assertEqual(call(client,body)[0],200)

    def test_concurrent_start_does_not_duplicate_or_extend(self):
        _,_,u,_=self.register()
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs=list(pool.map(lambda _:self.begin(u),range(2)))
        self.assertEqual(runs[0]['id'],runs[1]['id'])
        self.assertEqual(runs[0]['current']['deadline'],runs[1]['current']['deadline'])
        self.now=runs[0]['current']['deadline']
        result=t.answer(runs[0]['id'],t.Answer(item_id=runs[0]['current']['id'],action='confirm',expected_version=0),Response(),u)
        self.assertEqual(result['answers'][0]['status'],'expired')

    def test_confirmation_must_match_saved_selection_version(self):
        _,_,u,_=self.register();d=self.begin(u);i=d['current']
        t.selection(d['id'],t.Selection(item_id=i['id'],expected_version=0,choices=[self.fixture['keys'][0]]),Response(),u)
        with self.assertRaises(HTTPException) as conflict:
            t.answer(d['id'],t.Answer(item_id=i['id'],action='confirm',expected_version=0),Response(),u)
        self.assertEqual(conflict.exception.status_code,409)
        self.assertIsNone(t.resume(d['id'],Response(),u)['answers'][0]['status'])

    def test_answer_keys_unavailable_before_finish_and_for_other_student(self):
        _,_,u,_=self.register();_,_,v,_=self.register();d=self.begin(u)
        with self.runtime.begin() as c:
            t.scope(c,u)
            self.assertEqual(t.query(c,'SELECT * FROM learning.training_feedback(:id)',id=d['id']).all(),[])
            self.assertEqual(t.query(c,"SELECT has_table_privilege(current_user,'content.answer_keys','SELECT')").scalar_one(),False)
            t.scope(c,v)
            self.assertEqual(t.query(c,'SELECT * FROM learning.training_runs WHERE id=:id',id=d['id']).all(),[])

class MasteryPolicyTests(unittest.TestCase):
    def test_repeated_family_and_sparse_evidence_never_mean_mastered(self):
        now=datetime.now(timezone.utc)
        rows=[{'received_at':now,'family_id':'same','outcome':'correct','concepts':[{'id':'c','label':'test'}]} for _ in range(20)]
        d=summarize(rows,now)[0];self.assertEqual(d['evidence_count'],1);self.assertEqual(d['state'],'insufficient')
        rows[0]['outcome']='wrong';self.assertEqual(summarize(rows,now)[0]['score'],0)
    def test_no_data_and_old_data(self):
        now=datetime.now(timezone.utc)
        self.assertEqual(summarize([],now),[])
        self.assertEqual(summarize([{'received_at':now-timedelta(days=31),'concepts':[]}],now),[])
