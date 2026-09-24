import hashlib
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import test_school as school
from test_accounts import Client,owner_connect,PASSWORD
from provision_school import recover_account

class RecoveryTests(school.SchoolTests):
    def test_reset_one_use_rotation_and_session_invalidation(self):
        manager,m,teacher,t,student,s,code=self.family()
        body={'membership_id':s['membership_id'],'identity_confirmed':True}
        self.assertEqual(self.call(teacher,'/recovery',body)[0],403)
        self.assertEqual(self.call(manager,'/recovery',{'membership_id':m['membership_id'],'identity_confirmed':True})[0],404)
        self.assertEqual(self.call(manager,'/recovery',{'membership_id':s['membership_id'],'identity_confirmed':False})[0],422)
        status,old=self.call(manager,'/recovery',body);self.assertEqual(status,201,old)
        status,new=self.call(manager,'/recovery',body);self.assertEqual(status,201,new)
        self.assertEqual(student.call('/me')[0],200) # Issuing does not reset credentials.
        reset={'email':s['email'],'password':PASSWORD+'-new','recovery_code':old['recovery_code']}
        self.assertEqual(Client().call('/recover',reset)[0],400)
        reset['recovery_code']=new['recovery_code']
        with owner_connect(self.database) as c:old_hash=c.execute('SELECT password_hash FROM identity.local_accounts WHERE membership_id=%s',(s['membership_id'],)).fetchone()[0]
        self.assertEqual(Client().call('/recover',reset,origin='https://evil.test')[0],403)
        self.assertEqual(Client().call('/recover',{**reset,'email':t['email']})[0],400)
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes=list(pool.map(lambda _:Client().call('/recover',reset)[0],range(2)))
        self.assertEqual(sorted(codes),[200,400])
        self.assertEqual(student.call('/me')[0],401)
        self.assertEqual(Client().call('/login',{'email':s['email'],'password':PASSWORD})[0],401)
        self.assertEqual(Client().call('/login',{'email':s['email'],'password':reset['password']})[0],200)
        with owner_connect(self.database) as c:
            self.assertFalse(c.execute('SELECT identity.portal_new_session(%s,%s,%s)',(s['membership_id'],'a'*64,old_hash)).fetchone()[0])
            self.assertEqual(c.execute("SELECT count(*) FROM identity.account_access_audit WHERE membership_id=%s AND event='password_reset'",(s['membership_id'],)).fetchone()[0],1)
    def test_invitation_renew_cancel_stale_and_scope(self):
        manager,m,school_code=self.account('school_manager');email=uuid4().hex+'@example.test'
        status,first=self.call(manager,'/invite',{'email':email,'role':'student'});self.assertEqual(status,201)
        rows=self.call(manager,'/invitations')[1]['items'];row=rows[0];self.assertNotIn('token_hash',row)
        action={'invitation_id':row['id'],'expected_version':row['version']}
        foreign,f,_=self.account('school_manager')
        self.assertEqual(self.call(foreign,'/invitations/renew',action)[0],404)
        status,renewed=self.call(manager,'/invitations/renew',action);self.assertEqual(status,200,renewed)
        self.assertEqual(self.call(manager,'/invitations/revoke',action)[0],409)
        activation={'email':email,'password':PASSWORD,'display_name':'تجربة','invitation_code':first['invitation_code']}
        self.assertEqual(Client().call('/activate',activation)[0],400)
        row=self.call(manager,'/invitations')[1]['items'][0]
        self.assertEqual(self.call(manager,'/invitations/revoke',{'invitation_id':row['id'],'expected_version':row['version']})[0],200)
        self.assertEqual(Client().call('/activate',{**activation,'invitation_code':renewed['invitation_code']})[0],400)
        self.assertEqual(self.call(manager,'/invitations')[1]['items'][0]['state'],'revoked')
        self.assertEqual(self.call(manager,'/invitations?offset=50')[1]['items'],[])
    def test_expired_recovery_and_operator_manager_recovery(self):
        manager,m,school_code=self.account('school_manager')
        with owner_connect(self.database) as c:
            code=recover_account(c,school_code,m['email'])
            c.execute("UPDATE identity.account_recovery SET created_at=now()-interval '2 hours',expires_at=now()-interval '1 hour' WHERE membership_id=%s",(m['membership_id'],))
        body={'email':m['email'],'password':PASSWORD+'-changed','recovery_code':code['recovery_code']}
        self.assertEqual(Client().call('/recover',body)[0],400)
        with owner_connect(self.database) as c:code=recover_account(c,school_code,m['email'])
        self.assertEqual(Client().call('/recover',{**body,'recovery_code':code['recovery_code']})[0],200)
        self.assertEqual(manager.call('/me')[0],401)
        self.assertEqual(Client().call('/login',{'email':m['email'],'password':body['password']})[0],200)
    def test_expired_invite_can_be_renewed_and_used_invite_cannot(self):
        manager,m,school_code=self.account('school_manager');email=uuid4().hex+'@example.test'
        status,created=self.call(manager,'/invite',{'email':email,'role':'instructor'});self.assertEqual(status,201)
        row=self.call(manager,'/invitations')[1]['items'][0]
        with owner_connect(self.database) as c:c.execute("UPDATE identity.student_invitations SET created_at=now()-interval '5 days',expires_at=now()-interval '1 day' WHERE id=%s",(row['id'],))
        self.assertEqual(self.call(manager,'/invitations')[1]['items'][0]['state'],'expired')
        status,new=self.call(manager,'/invitations/renew',{'invitation_id':row['id'],'expected_version':row['version']});self.assertEqual(status,200,new)
        self.assertEqual(Client().call('/activate',{'email':email,'password':PASSWORD,'display_name':'أستاذ اختبار','invitation_code':new['invitation_code']})[0],201)
        row=self.call(manager,'/invitations')[1]['items'][0];self.assertEqual(row['state'],'used')
        self.assertEqual(self.call(manager,'/invitations/renew',{'invitation_id':row['id'],'expected_version':row['version']})[0],409)

    def test_suspension_revokes_recovery_and_private_storage(self):
        manager,m,teacher,t,student,s,school_code=self.family()
        body={'membership_id':s['membership_id'],'identity_confirmed':True}
        foreign,_,_=self.account('school_manager')
        self.assertEqual(self.call(foreign,'/recovery',body)[0],404)
        status,code=self.call(manager,'/recovery',body);self.assertEqual(status,201)
        self.assertEqual(self.call(manager,'/status',{'student_id':s['membership_id'],'status':'inactive'})[0],200)
        self.assertEqual(self.call(manager,'/status',{'student_id':s['membership_id'],'status':'active'})[0],200)
        self.assertEqual(Client().call('/recover',{'email':s['email'],'password':PASSWORD+'-new','recovery_code':code['recovery_code']})[0],400)
        import psycopg
        with owner_connect(self.database) as c:
            stored=c.execute('SELECT token_hash FROM identity.account_recovery WHERE membership_id=%s',(s['membership_id'],)).fetchone()[0]
            self.assertEqual(stored,hashlib.sha256(code['recovery_code'].encode()).hexdigest())
            c.execute('SET LOCAL ROLE sya9a_student_runtime')
            for query in ['SELECT * FROM identity.account_recovery','SELECT * FROM identity.account_access_audit',"SELECT identity.issue_account_recovery(NULL,NULL,NULL)"]:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with c.transaction():c.execute(query)
