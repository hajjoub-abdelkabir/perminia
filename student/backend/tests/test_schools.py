"""School activation and tenant isolation contracts, in disposable databases."""
import hashlib
import secrets
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from test_accounts import AccountTests, Client, PASSWORD, owner_connect
from provision_school import create_school, invite_student, revoke_invitation
import psycopg


class SchoolTests(AccountTests):
    def activate(self,email,token,extra=None):
        client=Client()
        body={'email':email,'display_name':'تلميذ المدرسة','password':PASSWORD,'invitation_code':token}
        body.update(extra or {})
        return client,client.call('/activate',body)

    def test_open_signup_and_privileged_provisioning_are_closed(self):
        self.assertEqual(Client().call('/register',{'email':'public@example.test','password':PASSWORD,'display_name':'زائر'})[0],410)
        with owner_connect(self.database) as c:
            c.execute('SET LOCAL ROLE sya9a_student_runtime')
            for table in ('identity.schools','identity.student_invitations','identity.provisioning_audit'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with c.transaction(): c.execute('SELECT * FROM '+table)
            with self.assertRaises(psycopg.Error):
                with c.transaction(): c.execute("SELECT identity.auth_register('a@b.test','name','hash','token')")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with c.transaction(): create_school(c,'forbidden','مدرسة ممنوعة')

    def test_email_binding_expiry_revocation_and_replay(self):
        email=uuid.uuid4().hex+'@example.test'
        invite=self.invitation(email)
        self.assertEqual(self.activate('wrong@example.test',invite['invitation_code'])[1][0],400)
        client,result=self.activate(email,invite['invitation_code'])
        self.assertEqual(result[0],201)
        user=result[1]['user']
        self.assertEqual(user['school_id'],user['tenant_id'])
        self.assertEqual(user['school_code'],invite['school_code'])
        self.assertEqual(self.activate(email,invite['invitation_code'])[1][0],400)
        for mode in ('expired','revoked'):
            email=uuid.uuid4().hex+'@example.test'
            pending=self.invitation(email)
            with owner_connect(self.database) as c:
                if mode=='revoked': revoke_invitation(c,pending['invitation_id'])
                else: c.execute("UPDATE identity.student_invitations SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE id=%s",(pending['invitation_id'],))
            self.assertEqual(self.activate(email,pending['invitation_code'])[1][0],400)

    def test_two_schools_rls_and_no_chosen_tenant(self):
        first,_,a,_=self.register('التلميذ أ')
        second,_,b,_=self.register('التلميذ ب')
        self.assertNotEqual(a['school_id'],b['school_id'])
        email=uuid.uuid4().hex+'@example.test'
        invite=self.invitation(email)
        self.assertEqual(self.activate(email,invite['invitation_code'],{'tenant_id':b['tenant_id']})[1][0],422)
        self.assertEqual(first.call('/me')[1]['user']['school_id'],a['school_id'])
        self.assertEqual(second.call('/me')[1]['user']['school_id'],b['school_id'])
        with owner_connect(self.database) as c:
            for student in (a,b):
                c.execute("INSERT INTO learning.learning_events(tenant_id,membership_id,event_type,occurred_at,payload,dedupe_key) VALUES(%s,%s,'test-school-isolation',now(),'{}',%s)",(student['tenant_id'],student['membership_id'],uuid.uuid4()))
        with owner_connect(self.database) as c:
            c.execute('SET LOCAL ROLE sya9a_student_runtime')
            self.assertEqual(c.execute('SELECT count(*) FROM learning.learning_events').fetchone()[0],0)
            for student in (a,b):
                c.execute("SELECT set_config('app.tenant_id',%s,true),set_config('app.membership_id',%s,true)",(student['tenant_id'],student['membership_id']))
                rows=c.execute('SELECT tenant_id,membership_id FROM learning.learning_events').fetchall()
                self.assertEqual([(str(x),str(y)) for x,y in rows],[(student['tenant_id'],student['membership_id'])])
            c.execute("SELECT set_config('app.tenant_id',%s,true),set_config('app.membership_id',%s,true)",(b['tenant_id'],a['membership_id']))
            self.assertEqual(c.execute('SELECT count(*) FROM learning.learning_events').fetchone()[0],0)

    def test_disabled_school_blocks_activation_and_existing_session(self):
        client,email,user,_=self.register()
        email2=uuid.uuid4().hex+'@example.test'
        invite=self.invitation(email2,user['school_code'])
        with owner_connect(self.database) as c:
            c.execute("UPDATE identity.tenants SET status='inactive' WHERE id=%s",(user['school_id'],))
        self.assertEqual(client.call('/me')[0],401)
        self.assertEqual(client.call('/login',{'email':email,'password':PASSWORD})[0],401)
        self.assertEqual(self.activate(email2,invite['invitation_code'])[1][0],400)

    def test_concurrent_redemption_only_creates_one_student(self):
        email=uuid.uuid4().hex+'@example.test'
        invite=self.invitation(email)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:self.activate(email,invite['invitation_code'])[1][0],range(2)))
        self.assertEqual(sorted(responses),[201,400])
        with owner_connect(self.database) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM identity.local_accounts WHERE email=%s',(email,)).fetchone()[0],1)
            self.assertEqual(c.execute("SELECT count(*) FROM identity.provisioning_audit WHERE invitation_id=%s AND event_type='student_activated'",(invite['invitation_id'],)).fetchone()[0],1)
            stored=c.execute('SELECT token_hash FROM identity.student_invitations WHERE id=%s',(invite['invitation_id'],)).fetchone()[0]
            self.assertEqual(stored,hashlib.sha256(invite['invitation_code'].encode()).hexdigest())

    def test_reissuing_invite_revokes_old_code(self):
        email=uuid.uuid4().hex+'@example.test'
        first=self.invitation(email)
        second=self.invitation(email,first['school_code'])
        self.assertEqual(self.activate(email,first['invitation_code'])[1][0],400)
        self.assertEqual(self.activate(email,second['invitation_code'])[1][0],201)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SchoolTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
