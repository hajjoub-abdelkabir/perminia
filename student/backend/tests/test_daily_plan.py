import unittest
import json
from datetime import datetime,timezone
from urllib.request import Request
from urllib.error import HTTPError
import test_lessons as lessons
from test_accounts import Client,owner_connect
from app.daily_plan import arrange

class DailyPlanTests(lessons.LessonTests):
    def plan(self,client):
        try:
            with client.opener.open(Request('http://127.0.0.1:8099/api/v1/student/journey/daily-plan')) as r:
                self.assertEqual(r.headers['Cache-Control'],'no-store');return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)

    def test_real_completion_bookmark_and_member_isolation(self):
        one,_,u,_=self.register();two,_,_,_=self.register()
        code,p=self.plan(one);self.assertEqual(code,200);self.assertEqual(p['completed_today'],0)
        first=p['tasks'][0];route='/lesson-progress/'+first['revision_id']
        self.api(one,route,{'section_position':first['position'],'bookmarked':True},'PUT')
        self.assertEqual(self.plan(one)[1]['completed_today'],0)
        for _ in range(2):self.api(one,route,{'section_position':first['position'],'completed':True},'PUT')
        p=self.plan(one)[1];self.assertEqual(p['completed_today'],1)
        self.assertEqual(len(p['tasks']),p['target']-1)
        self.assertEqual(p['bookmarks'][0]['position'],first['position'])
        self.assertEqual(self.plan(two)[1]['completed_today'],0)
        self.assertEqual(self.plan(Client())[0],401)

    def test_historical_backfill_not_counted_as_today(self):
        client,_,u,_=self.register();first=self.plan(client)[1]['tasks'][0]
        self.api(client,'/lesson-progress/'+first['revision_id'],{'section_position':first['position'],'completed':True},'PUT')
        with owner_connect(self.database) as c:
            c.execute("UPDATE learning.reading_activity SET origin='latest_state_backfill' WHERE membership_id=%s",(u['membership_id'],))
        self.assertEqual(self.plan(client)[1]['completed_today'],0)

class ArrangementTests(unittest.TestCase):
    def rows(self,count=8):return [dict(position=i,completed=False,done_today=False,updated_at=None,bookmarked=False) for i in range(1,count+1)]
    def test_budget_and_goal_met(self):
        rows=self.rows();self.assertEqual(arrange(rows,5)['target'],1);self.assertEqual(arrange(rows,120)['target'],6)
        for r in rows[:4]:r.update(completed=True,done_today=True)
        p=arrange(rows,20);self.assertTrue(p['target_met']);self.assertEqual(p['tasks'],[])
    def test_old_completion_uncompleted_and_latest_resume(self):
        rows=self.rows();rows[0].update(completed=True);rows[1].update(done_today=True)
        rows[3]['updated_at']=datetime.now(timezone.utc)
        p=arrange(rows,10);self.assertEqual(p['completed_today'],0);self.assertEqual(p['tasks'][0]['position'],2);self.assertEqual(p['resume']['position'],4)
    def test_empty_and_all_read(self):
        self.assertFalse(arrange([],20)['all_read']);self.assertIsNone(arrange([],20)['resume'])
        rows=self.rows();[r.update(completed=True) for r in rows]
        p=arrange(rows,20);self.assertTrue(p['all_read']);self.assertEqual(p['tasks'],[])

if __name__=='__main__':unittest.main()
