import unittest,json
from datetime import timedelta
from uuid import uuid4
from urllib.request import Request
from urllib.error import HTTPError
import test_lessons as lessons
from test_accounts import Client,owner_connect
from training_fixture import install

class NotebookTests(lessons.LessonTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with owner_connect(cls.database) as c:cls.questions=install(c)

    def call(self,client,path='',body=None,method=None,origin='http://localhost:5174'):
        req=Request('http://127.0.0.1:8099/api/v1/student/journey/notebook'+path,data=json.dumps(body).encode() if body is not None else None,
          method=method,headers={'Content-Type':'application/json','Origin':origin,'X-Sya9a-Request':'student'})
        try:
            with client.opener.open(req) as r:
                self.assertEqual(r.headers['Cache-Control'],'no-store');return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)

    def add(self,client):
        rev=self.api(client,'/lessons')[1]['items'][0]['revision_id']
        body={'kind':'lesson','revision_id':rev,'section_position':1,'reason':'unclear','note':'ملاحظة اختبار'}
        code,d=self.call(client,body=body);self.assertEqual(code,200);return d['id'],body

    def test_deduplication_member_isolation_and_no_answers(self):
        c,_,u,_=self.register();other,_,_,_=self.register();ident,body=self.add(c)
        self.assertEqual(self.call(c,body=body)[1]['id'],ident)
        p=self.call(c)[1];self.assertEqual(len(p['items']),1);self.assertEqual(p['due_count'],1)
        self.assertEqual(self.call(other)[1]['items'],[])
        self.assertEqual(self.call(Client())[0],401)
        self.assertEqual(self.call(other,'/'+ident,{'expected_version':1,'action':'close'},'PATCH')[0],404)
        self.call(c,body={'kind':'question','revision_id':str(self.questions['revisions'][0]),'reason':'hesitated'})
        item=next(x for x in self.call(c)[1]['items'] if x['kind']=='question')
        self.assertTrue(item['available']);self.assertTrue(item['image_url'])
        self.assertNotIn('correct_choices',json.dumps(item));self.assertNotIn('answer_key',json.dumps(item))

    def test_schedule_review_and_daily_deduplication(self):
        c,_,_,_=self.register();ident,body=self.add(c)
        self.assertEqual(self.call(c,'/'+ident,{'expected_version':1,'action':'snooze','days':3},'PATCH')[0],200)
        d=self.call(c)[1];self.assertEqual(d['due_count'],0);self.assertEqual(d['week']['reviews'],0)
        due=d['items'][0]['due_on'];self.call(c,body=body);self.assertEqual(self.call(c)[1]['items'][0]['due_on'],due)
        self.assertEqual(self.call(c,'/'+ident,{'expected_version':1,'action':'close'},'PATCH')[0],409)
        self.call(c,'/'+ident,{'expected_version':2,'action':'review','days':7},'PATCH')
        self.call(c,'/'+ident,{'expected_version':3,'action':'close'},'PATCH')
        d=self.call(c)[1];self.assertEqual(d['week']['reviews'],1);self.assertEqual(d['items'][0]['state'],'done')
        self.call(c,'/'+ident,{'expected_version':4,'action':'reopen'},'PATCH')
        self.assertEqual(self.call(c)[1]['due_count'],1)

    def test_target_scope_validation_and_origin(self):
        c,_,u,_=self.register();ident,body=self.add(c)
        self.assertEqual(self.call(c,body={**body,'revision_id':str(uuid4())})[0],404)
        self.assertEqual(self.call(c,body={**body,'note':'x'*601})[0],422)
        self.assertEqual(self.call(c,body={**body,'membership_id':str(uuid4())})[0],422)
        self.assertEqual(self.call(c,body={**body,'kind':'question'})[0],422)
        self.assertEqual(self.call(c,body=body,origin='https://other.test')[0],403)
        self.assertEqual(self.call(c,'/'+ident,{'expected_version':1,'action':'close'},'PATCH',origin='https://other.test')[0],403)
        self.assertEqual(self.call(c,'/'+ident,{'unexpected':'x'*140000},'PATCH')[0],413)
        with owner_connect(self.database) as db:
            db.execute('SET LOCAL ROLE sya9a_student_runtime')
            self.assertEqual(db.execute('SELECT count(*) FROM learning.review_notebook').fetchone()[0],0)

    def test_week_ignores_old_reviews_and_backfill(self):
        c,_,u,_=self.register();ident,body=self.add(c)
        self.call(c,'/'+ident,{'expected_version':1,'action':'close'},'PATCH')
        with owner_connect(self.database) as db:
            db.execute("UPDATE learning.notebook_activity SET day=day-8 WHERE membership_id=%s",(u['membership_id'],))
        d=self.call(c)[1];self.assertEqual(d['week']['reviews'],0);self.assertEqual(d['week']['badges'],[])

if __name__=='__main__':unittest.main()
