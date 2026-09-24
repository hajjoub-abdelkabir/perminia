"""Exercise imports and lesson progress against a disposable database/API."""
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import json
from urllib.request import Request
from urllib.error import HTTPError
from test_accounts import AccountTests, Client, owner_connect
import import_courses

class LessonTests(AccountTests):
    @classmethod
    def setUpClass(cls):
        os.environ['STUDENT_PREVIEW_ENABLED']='true'
        super().setUpClass()
        cls.media=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.media.cleanup)
        with patch.object(import_courses,'connect',lambda:owner_connect(cls.database)):
            import_courses.run(Path('/imports'),Path(cls.media.name),False)
            import_courses.run(Path('/imports'),Path(cls.media.name),False)

    def api(self,client,path,body=None,method=None,origin='http://localhost:5174'):
        req=Request('http://127.0.0.1:8099/api/v1/student/preview'+path,
            data=json.dumps(body).encode() if body is not None else None,method=method,
            headers={'Origin':origin,'X-Sya9a-Request':'student','Content-Type':'application/json'})
        try:
            with client.opener.open(req,timeout=10) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)

    def test_import_counts_and_draft_boundary(self):
        status,body=self.api(Client(),'/lessons');self.assertEqual(status,200);self.assertEqual(len(body['items']),10)
        self.assertTrue(all(l['status']=='draft' for l in body['items']))
        with owner_connect(self.database) as c:
            for table,count in [('lessons',10),('lesson_revisions',10),('lesson_sections',40),('road_sign_revisions',253)]:
                self.assertEqual(c.execute('SELECT count(*) FROM content.'+table).fetchone()[0],count)
            self.assertEqual(c.execute('SELECT count(*) FROM content.knowledge_chunks').fetchone()[0],0)
        self.assertEqual(len(self.api(Client(),'/signs')[1]['items']),253)

    def test_progress_bookmark_retry_and_school_isolation(self):
        one,_,u,_=self.register();two,_,v,_=self.register()
        rev=self.api(one,'/lessons')[1]['items'][0]['revision_id']
        route='/lesson-progress/'+rev
        for _ in range(2):self.assertEqual(self.api(one,route,{'section_position':1,'completed':True},'PUT')[0],200)
        self.assertEqual(self.api(one,route,{'section_position':1,'bookmarked':True},'PUT')[0],200)
        self.assertEqual(self.api(one,route,{'section_position':1},'PUT')[0],200)
        saved=self.api(one,'/lesson-progress')[1]['items'];self.assertEqual(len(saved),1)
        self.assertTrue(saved[0]['completed']);self.assertTrue(saved[0]['bookmarked'])
        with owner_connect(self.database) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM learning.reading_activity WHERE membership_id=%s',(u['membership_id'],)).fetchone()[0],1)
        self.assertEqual(self.api(two,'/lesson-progress')[1]['items'],[])
        self.assertEqual(self.api(Client(),'/lesson-progress')[0],401)
        self.assertEqual(self.api(one,route,{'section_position':99},'PUT')[0],404)
        self.assertEqual(self.api(one,route,{'section_position':1,'tenant_id':v['tenant_id']},'PUT')[0],422)
        self.assertEqual(self.api(one,route,{'section_position':1},'PUT',origin='https://other.test')[0],403)
        with owner_connect(self.database) as c:
            c.execute('SET LOCAL ROLE sya9a_student_runtime')
            self.assertEqual(c.execute('SELECT count(*) FROM learning.lesson_section_progress').fetchone()[0],0)
            c.execute("SELECT set_config('app.tenant_id',%s,true),set_config('app.membership_id',%s,true)",(str(v['tenant_id']),str(u['membership_id'])))
            self.assertEqual(c.execute('SELECT count(*) FROM learning.lesson_section_progress').fetchone()[0],0)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LessonTests))
    raise SystemExit(not result.wasSuccessful())
