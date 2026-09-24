"""Account integration tests use a disposable DB and separate local API process."""
import hashlib
import http.cookiejar
import json
import os
import secrets
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
import psycopg
from psycopg import sql
from provision_school import create_school, invite_student

ORIGIN = 'http://localhost:5174'
URL = 'http://127.0.0.1:8099/api/v1/auth'
PASSWORD = 'test-only-' + secrets.token_urlsafe(20)


def owner_connect(database=None):
    return psycopg.connect(host=os.environ.get('POSTGRES_HOST','db'), user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'], dbname=database or os.environ['POSTGRES_DB'])


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def call(self, route, body=None, extra_headers=None, origin=ORIGIN):
        headers = {'Origin': origin, 'X-Sya9a-Request': 'student'}
        if body is not None:
            headers['Content-Type']='application/json'
        headers.update(extra_headers or {})
        request = Request(URL+route, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, json.load(response), response.headers
        except HTTPError as response:
            return response.code, json.load(response), response.headers

    def token(self):
        return next(cookie.value for cookie in self.jar if cookie.name=='sya9a_student_session')


class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database='sya9a_student_test_auth_'+uuid.uuid4().hex[:12]
        cls.process=None
        with owner_connect() as connection:
            connection.autocommit=True
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.database)))
        cls.addClassCleanup(cls.cleanup)
        migration_env=dict(os.environ,POSTGRES_DB=cls.database)
        subprocess.run(['alembic','upgrade','head'],env=migration_env,check=True)
        runtime_env=dict(migration_env,POSTGRES_USER='sya9a_student_runtime',POSTGRES_PASSWORD=os.environ['RUNTIME_DB_PASSWORD'], STUDENT_COOKIE_SECURE='false')
        cls.process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8099','--no-access-log'],env=runtime_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                if Client().call('/me')[0]==401:
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError('Temporary API failed to start')

    @classmethod
    def cleanup(cls):
        if cls.process:
            cls.process.terminate()
            cls.process.wait(timeout=10)
        assert cls.database.startswith('sya9a_student_test_auth_')
        with owner_connect() as connection:
            connection.autocommit=True
            connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.database)))

    def invitation(self, email, school_code=None):
        school_code=school_code or 'school-'+uuid.uuid4().hex[:10]
        with owner_connect(self.database) as connection:
            create_school(connection,school_code,'مدرسة تجريبية '+school_code)
            return invite_student(connection,school_code,email)

    def register(self, name='متعلم تجريبي'):
        client=Client()
        email=uuid.uuid4().hex+'@example.test'
        invite=self.invitation(email)
        status,data,headers=client.call('/activate',{'email':email,'password':PASSWORD,'display_name':name,'invitation_code':invite['invitation_code']})
        self.assertEqual(status,201,data)
        return client,email,data['user'],headers

    def test_registration_persistence_and_private_storage(self):
        client,email,user,headers=self.register()
        self.assertEqual(client.call('/me')[1]['user'],user)
        self.assertEqual(user['email'],email)
        self.assertNotIn('password',json.dumps(user))
        cookie=headers['Set-Cookie']
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=strict',cookie)
        self.assertIn('Path=/api',cookie)
        self.assertEqual(headers['Cache-Control'],'no-store')
        with owner_connect(self.database) as connection:
            record=connection.execute('SELECT a.password_hash,m.role,p.category_id FROM identity.local_accounts a JOIN identity.memberships m ON m.id=a.membership_id JOIN identity.learner_profiles p ON p.membership_id=m.id WHERE a.email=%s',(email,)).fetchone()
            self.assertTrue(record[0].startswith('scrypt-v1$'))
            self.assertNotIn(PASSWORD,record[0])
            self.assertEqual(record[1:],('student','B'))
            stored=connection.execute('SELECT token_hash FROM identity.local_sessions WHERE membership_id=%s',(user['membership_id'],)).fetchone()[0]
            self.assertEqual(stored,hashlib.sha256(client.token().encode()).hexdigest())
            self.assertNotEqual(stored,client.token())
            connection.execute('SET LOCAL ROLE sya9a_student_runtime')
            for table in ('identity.local_accounts','identity.local_sessions','content.answer_keys'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction():
                        connection.execute('SELECT * FROM '+table)

    def test_login_logout_rotation_and_wrong_password(self):
        client,email,user,_=self.register()
        old=client.token()
        self.assertEqual(Client().call('/login',{'email':email,'password':'wrong'})[0],401)
        status,body,_=client.call('/login',{'email':email.upper(),'password':PASSWORD})
        self.assertEqual(status,200)
        self.assertEqual(body['user']['membership_id'],user['membership_id'])
        self.assertNotEqual(client.token(),old)
        attacker=Client()
        self.assertEqual(attacker.call('/me',extra_headers={'Cookie':'sya9a_student_session='+old})[0],401)
        active=client.token()
        self.assertEqual(client.call('/logout',{})[0],200)
        self.assertEqual(client.call('/me')[0],401)
        self.assertEqual(attacker.call('/me',extra_headers={'Cookie':'sya9a_student_session='+active})[0],401)
        self.assertEqual(client.call('/logout',{})[0],200)

    def test_two_students_and_duplicate_email(self):
        first,email,user,_=self.register('التلميذ الأول')
        second,_,other,_=self.register('التلميذ الثاني')
        self.assertNotEqual(user['membership_id'],other['membership_id'])
        self.assertEqual(first.call('/me')[1]['user']['display_name'],'التلميذ الأول')
        self.assertEqual(second.call('/me')[1]['user']['display_name'],'التلميذ الثاني')
        # Synthetic duplicate invitation tests atomic rejection; production CLI refuses this.
        token=secrets.token_urlsafe(32)
        with owner_connect(self.database) as connection:
            school=create_school(connection,'dup-'+uuid.uuid4().hex[:8],'مدرسة أخرى')['school_id']
            connection.execute("INSERT INTO identity.student_invitations(school_id,email,token_hash,expires_at) VALUES(%s,%s,%s,now()+interval '1 hour')",(school,email,hashlib.sha256(token.encode()).hexdigest()))
        duplicate=Client().call('/activate',{'email':email.upper(),'display_name':'مكرر','password':PASSWORD,'invitation_code':token})
        self.assertEqual(duplicate[0],409)
        with owner_connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM identity.local_accounts WHERE email=%s',(email,)).fetchone()[0],1)
            self.assertEqual(connection.execute('SELECT count(*) FROM identity.users u WHERE NOT EXISTS(SELECT 1 FROM identity.memberships m WHERE m.user_id=u.id)').fetchone()[0],0)

    def test_expired_and_inactive_sessions(self):
        client,email,user,_=self.register()
        with owner_connect(self.database) as connection:
            connection.execute("UPDATE identity.local_sessions SET expires_at=now()-interval '1 second' WHERE membership_id=%s",(user['membership_id'],))
        self.assertEqual(client.call('/me')[0],401)
        self.assertEqual(client.call('/login',{'email':email,'password':PASSWORD})[0],200)
        with owner_connect(self.database) as connection:
            connection.execute("UPDATE identity.memberships SET status='inactive' WHERE id=%s",(user['membership_id'],))
        self.assertEqual(client.call('/me')[0],401)
        self.assertEqual(client.call('/login',{'email':email,'password':PASSWORD})[0],401)

    def test_origin_validation_no_password_echo_and_no_escalation(self):
        client=Client()
        body={'email':'csrf@example.test','password':PASSWORD,'display_name':'متعلم','invitation_code':secrets.token_urlsafe(32)}
        self.assertEqual(client.call('/activate',body,origin='https://untrusted.example')[0],403)
        self.assertEqual(client.call('/activate',body,origin='')[0],403)
        self.assertEqual(client.call('/activate',body,extra_headers={'X-Sya9a-Request':''})[0],403)
        status,data,_=client.call('/activate',{**body,'role':'admin'})
        self.assertEqual(status,422)
        self.assertNotIn(PASSWORD,json.dumps(data))
        self.assertEqual(client.call('/activate',{**body,'password':'short'})[0],422)
        self.assertEqual(client.call('/activate',{**body,'display_name':'  '})[0],422)
        self.assertEqual(client.call('/activate',{**body,'email':'bad-address'})[0],422)

    def test_rate_limit_is_persisted_and_bounded(self):
        client=Client()
        email=uuid.uuid4().hex+'@example.test'
        for _ in range(10):
            self.assertEqual(client.call('/login',{'email':email,'password':PASSWORD})[0],401)
        status,_,headers=Client().call('/login',{'email':email,'password':PASSWORD})
        self.assertEqual(status,429)
        self.assertEqual(headers['Retry-After'],'900')

    def test_oversized_body_and_failed_response_not_cached(self):
        status,_,headers=Client().call('/login',{'email':'body@example.test','password':'x'*9000})
        self.assertEqual(status,413)
        self.assertEqual(headers['Cache-Control'],'no-store')
        status,_,headers=Client().call('/me')
        self.assertEqual(status,401)
        self.assertEqual(headers['Cache-Control'],'no-store')

if __name__=='__main__':
    unittest.main(verbosity=2)

