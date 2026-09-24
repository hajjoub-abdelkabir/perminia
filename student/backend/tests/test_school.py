import json
from uuid import uuid4
from urllib.request import Request
from urllib.error import HTTPError
import test_lessons as lessons
from test_accounts import Client,owner_connect,PASSWORD
from provision_school import create_school,invite_student
from training_fixture import install

class SchoolTests(lessons.LessonTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with owner_connect(cls.database) as c:cls.fixture=install(c)
    def call(self,client,path,body=None,origin='http://localhost:5174'):
        req=Request('http://127.0.0.1:8099/api/v1/school'+path,data=None if body is None else json.dumps(body).encode(),headers={'Origin':origin,'Content-Type':'application/json','X-Sya9a-Request':'student'})
        try:
            with client.opener.open(req) as r:
                self.assertEqual(r.headers['Cache-Control'],'no-store');return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)
    def account(self,role,school=None):
        school=school or 'portal-'+uuid4().hex[:10];email=uuid4().hex+'@example.test'
        with owner_connect(self.database) as c:
            create_school(c,school,'Portal '+school)
            invite=invite_student(c,school,email,role=role)
        client=Client();status,data,_=client.call('/activate',dict(email=email,password=PASSWORD,display_name='اختبار '+role,invitation_code=invite['invitation_code']))
        self.assertEqual(status,201,data);self.assertEqual(data['user']['role'],role)
        return client,data['user'],school
    def family(self):
        manager,m,school=self.account('school_manager');teacher,t,_=self.account('instructor',school);student,s,_=self.account('student',school)
        return manager,m,teacher,t,student,s,school
    def link(self,manager,s,t,expected=None):
        status,d=self.call(manager,'/link',dict(student_id=s['membership_id'],teacher_id=t['membership_id'] if t else None,expected_link_id=expected));self.assertEqual(status,200,d)
    def test_full_lesson_assignment_lifecycle_and_idempotency(self):
        manager,m,teacher,t,student,s,school=self.family()
        self.assertEqual(self.call(teacher,'/roster')[1]['items'],[])
        self.link(manager,s,t)
        self.assertEqual(self.call(teacher,'/roster')[1]['items'][0]['id'],s['membership_id'])
        lesson=self.api(student,'/lessons')[1]['items'][0]
        payload=dict(student_id=s['membership_id'],kind='lesson',target_id=lesson['revision_id'],note='راجع الصور')
        for _ in range(2):self.assertEqual(self.call(teacher,'/assign',payload)[0],200)
        tasks=self.call(student,'/my-tasks')[1]['items'];self.assertEqual(len(tasks),1);self.assertFalse(tasks[0]['ready']);task=tasks[0]['id']
        self.assertEqual(self.call(student,'/complete',{'task_id':task})[0],409)
        for n in range(1,lesson['section_count']+1):
            self.assertEqual(self.api(student,'/lesson-progress/'+lesson['revision_id'],dict(section_position=n,completed=True),'PUT')[0],200)
        self.assertTrue(self.call(student,'/my-tasks')[1]['items'][0]['ready'])
        for _ in range(2):self.assertEqual(self.call(student,'/complete',{'task_id':task})[0],200)
        detail=self.call(teacher,'/students/'+s['membership_id'])[1];self.assertEqual(detail['tasks'][0]['state'],'done')
        self.assertEqual(detail['lessons'][0]['completed_sections'],lesson['section_count'])
    def test_role_tenant_and_reassignment_boundaries(self):
        manager,m,teacher,t,student,s,school=self.family();other,ot,_=self.account('instructor',school);foreign,f,_=self.account('school_manager')
        self.link(manager,s,t)
        self.assertEqual(self.api(teacher,'/lesson-progress')[0],403)
        self.assertEqual(self.call(student,'/roster')[0],403)
        self.assertEqual(self.call(other,'/students/'+s['membership_id'])[0],404)
        self.assertEqual(self.call(foreign,'/students/'+s['membership_id'])[0],404)
        self.assertEqual(self.call(student,'/link',dict(student_id=s['membership_id'],teacher_id=t['membership_id'],expected_link_id=None))[0],403)
        self.assertEqual(self.call(manager,'/link',dict(student_id=s['membership_id'],teacher_id=f['membership_id'],expected_link_id=None))[0],409)
        row=next(x for x in self.call(manager,'/roster')[1]['items'] if x['id']==s['membership_id'])
        self.link(manager,s,ot,row['link_id'])
        self.assertEqual(self.call(teacher,'/students/'+s['membership_id'])[0],404)
        self.assertEqual(self.call(other,'/students/'+s['membership_id'])[0],200)
        self.assertEqual(self.call(manager,'/status',dict(student_id=ot['membership_id'],status='inactive'))[0],200)
        self.assertEqual(other.call('/me')[0],401)
        self.assertEqual(self.call(manager,'/status',dict(student_id=ot['membership_id'],status='active'))[0],200)
        self.assertEqual(other.call('/me')[0],401) # Reactivation cannot resurrect old sessions.
        self.assertEqual(Client().call('/login',dict(email=t['email'],password=PASSWORD))[1]['user']['role'],'instructor')
    def test_invites_permission_and_activation(self):
        manager,m,teacher,t,student,s,school=self.family()
        email=uuid4().hex+'@example.test';body={'email':email,'role':'instructor'}
        self.assertEqual(self.call(teacher,'/invite',body)[0],403)
        self.assertEqual(self.call(manager,'/invite',body,origin='https://evil.test')[0],403)
        self.assertEqual(self.call(manager,'/invite',{**body,'role':'school_manager'})[0],422)
        status,invite=self.call(manager,'/invite',body);self.assertEqual(status,201,invite)
        self.assertEqual(self.call(manager,'/invite',body)[0],409)
        client=Client();status,d,_=client.call('/activate',dict(email=email,password=PASSWORD,display_name='أستاذ جديد',invitation_code=invite['invitation_code']))
        self.assertEqual(status,201,d);self.assertEqual(d['user']['role'],'instructor');self.assertEqual(d['user']['tenant_id'],m['tenant_id'])
        self.assertEqual(self.call(client,'/roster')[1]['items'],[])
        with owner_connect(self.database) as c:
            c.execute('SET LOCAL ROLE sya9a_student_runtime')
            for table in ['identity.school_student_links','learning.school_tasks']:
                import psycopg
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with c.transaction():c.execute('SELECT * FROM '+table)
    def test_series_requires_new_confirmed_training_and_cancel(self):
        manager,m,teacher,t,student,s,school=self.family();self.link(manager,s,t)
        payload=dict(student_id=s['membership_id'],kind='series',target_id=str(self.fixture['series']))
        self.assertEqual(self.call(teacher,'/assign',payload)[0],200)
        task=self.call(student,'/my-tasks')[1]['items'][0]
        self.assertFalse(task['ready']);self.assertEqual(self.call(student,'/complete',{'task_id':task['id']})[0],409)
        def training(path='',body=None,method=None):
            req=Request('http://127.0.0.1:8099/api/v1/student/training'+path,data=None if body is None else json.dumps(body).encode(),method=method,headers={'Origin':'http://localhost:5174','Content-Type':'application/json','X-Sya9a-Request':'student'})
            with student.opener.open(req) as r:return json.load(r)
        run=training('',{'request_id':str(uuid4()),'mode':'preview','series_id':str(self.fixture['series'])})
        first=run['current'];training('/'+run['id']+'/selection',{'item_id':first['id'],'expected_version':0,'choices':[str(self.fixture['keys'][0])]},'PUT')
        run=training('/'+run['id']+'/answer',{'item_id':first['id'],'action':'confirm','expected_version':1})
        while run['current']:run=training('/'+run['id']+'/answer',{'item_id':run['current']['id'],'action':'skip'})
        self.assertTrue(self.call(student,'/my-tasks')[1]['items'][0]['ready'])
        self.assertEqual(self.call(student,'/complete',{'task_id':task['id']})[0],200)
        self.assertEqual(self.call(teacher,'/assign',payload)[0],200)
        newer=self.call(student,'/my-tasks')[1]['items'][0];self.assertFalse(newer['ready'])
        self.assertEqual(self.call(teacher,'/cancel',dict(student_id=s['membership_id'],task_id=newer['id']))[0],200)
        self.assertEqual(self.call(student,'/complete',{'task_id':newer['id']})[0],409)
