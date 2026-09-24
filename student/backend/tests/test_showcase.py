"""Publishable smoke suite: uses no imported files, real credentials or AI calls."""
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from test_accounts import AccountTests, Client, owner_connect
from test_training import TrainingTests, MasteryPolicyTests
from test_chat import ChatPureTests, ChatTests
from seed_showcase import seed


class ShowcaseTests(AccountTests):
    def test_seed_guards_idempotency_and_three_role_logins(self):
        import json
        with tempfile.TemporaryDirectory() as directory, owner_connect(self.database) as c:
            root = Path(directory)
            with patch.dict(os.environ, {'PERMINIA_SYNTHETIC_SHOWCASE':'false'}):
                with self.assertRaises(ValueError):
                    seed(c, root, root/'accounts.json')
            # AccountTests methods share a database; fixtures require a pristine DB.
            if c.execute('SELECT EXISTS(SELECT 1 FROM identity.users)').fetchone()[0]:
                with patch.dict(os.environ, {'PERMINIA_SYNTHETIC_SHOWCASE':'true'}):
                    with self.assertRaises(ValueError):
                        seed(c, root, root/'accounts.json')


class FreshShowcaseTests(AccountTests):
    @classmethod
    def setUpClass(cls):
        os.environ['STUDENT_PREVIEW_ENABLED'] = 'true'
        super().setUpClass()

    # Override inherited tests below at suite selection, so this DB starts empty.
    def test_fresh_showcase(self):
        import json
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'PERMINIA_SYNTHETIC_SHOWCASE':'true'}):
            root = Path(directory)
            with owner_connect(self.database) as c:
                self.assertEqual(seed(c,root,root/'accounts.json')['accounts'],6)
                self.assertEqual(seed(c,root,root/'accounts.json')['status'],'already_seeded')
                self.assertEqual(c.execute('SELECT count(*) FROM content.training_pool WHERE status=\'published\'').fetchone()[0],8)
            clients = {}
            for account in json.loads((root/'accounts.json').read_text(encoding='utf-8'))['accounts']:
                client = Client()
                status, body, _ = client.call('/login', {k:account[k] for k in ('email','password')})
                self.assertEqual(status,200)
                self.assertEqual(body['user']['role'], account['role'])
                clients[(account['school'],account['role'])] = (client, body['user'])
            from urllib.request import Request
            from urllib.error import HTTPError

            def api(client, route, body=None, method=None):
                request = Request('http://127.0.0.1:8099/api/v1/'+route,
                    data=None if body is None else json.dumps(body).encode(), method=method,
                    headers={'Origin':'http://localhost:5174','X-Sya9a-Request':'student','Content-Type':'application/json'})
                try:
                    with client.opener.open(request) as response:
                        return response.status, json.load(response)
                except HTTPError as response:
                    return response.code, json.load(response)

            student, user = clients[('showcase-atlas','student')]
            teacher, _ = clients[('showcase-atlas','instructor')]
            other, _ = clients[('showcase-rif','instructor')]
            status, tasks = api(student,'school/my-tasks')
            self.assertEqual(status,200)
            task = tasks['items'][0]
            self.assertFalse(task['ready'])
            for position in (2,3):
                status, _ = api(student,'student/preview/lesson-progress/'+task['target_id'],
                                {'section_position':position,'completed':True},'PUT')
                self.assertEqual(status,200)
            self.assertEqual(api(student,'school/complete',{'task_id':task['id']})[0],200)
            status, detail = api(teacher,'school/students/'+user['membership_id'])
            self.assertEqual(status,200)
            self.assertEqual(detail['tasks'][0]['state'],'done')
            self.assertEqual(api(other,'school/students/'+user['membership_id'])[0],404)


def load_tests(loader, tests, pattern):
    import unittest
    suite = unittest.TestSuite()
    for case in (ShowcaseTests, TrainingTests, MasteryPolicyTests, ChatPureTests, ChatTests):
        suite.addTests(loader.loadTestsFromTestCase(case))
    suite.addTest(FreshShowcaseTests('test_fresh_showcase'))
    return suite
