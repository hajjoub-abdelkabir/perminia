"""Integration suite runs exclusively in a disposable DB on our PostgreSQL container."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid
import psycopg
from psycopg import sql
from import_dataset import connect, run, uid

class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=os.environ['POSTGRES_DB']
        cls.database='sya9a_student_test_'+uuid.uuid4().hex[:12]
        with connect() as c:
            c.autocommit=True
            c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.database)))
        cls.addClassCleanup(cls.cleanup_database)
        os.environ['POSTGRES_DB']=cls.database
        subprocess.run(['alembic','upgrade','head'],check=True)
        cls.files=tempfile.TemporaryDirectory()
        cls.content=Path(cls.files.name)/'content'
        cls.source=Path(cls.files.name)/'source'
        shutil.copytree('/imports',cls.source)
        cls.expected_audio_assets=len({hashlib.sha256(p.read_bytes()).hexdigest() for p in (cls.source/'audio').rglob('*.mp3')})
        cls.report=run(cls.source,cls.content)

    @classmethod
    def cleanup_database(cls):
        os.environ['POSTGRES_DB']=cls.original
        with connect() as c:
            c.autocommit=True
            if not cls.database.startswith('sya9a_student_test_'): raise ValueError('Unexpected DB target')
            c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.database)))
        if hasattr(cls,'files'): cls.files.cleanup()

    def setUp(self): self.c=connect()
    def tearDown(self): self.c.rollback();self.c.close()
    def scalar(self,query,args=()): return self.c.execute(query,args).fetchone()[0]
    def fails(self,query,args=()):
        with self.assertRaises(psycopg.Error):
            with self.c.transaction(): self.c.execute(query,args)

    def test_01_import_and_replay(self):
        self.assertEqual(self.report['records'],400)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.choices'),1005)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.assessment_items'),400)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.media_assets WHERE availability=%s',('local',)),435+self.expected_audio_assets)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.media_assets WHERE availability=%s',('remote_only',)),0)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.question_revisions WHERE needs_prompt_reconstruction'),47)
        self.assertEqual(self.scalar("SELECT count(*) FROM content.question_localizations WHERE prompt=''"),47)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.published_question_prompts'),0)
        self.assertEqual(run(self.source,self.content)['status'],'already_imported')
        self.assertEqual(self.scalar('SELECT count(*) FROM ingestion.import_batches'),1)

    def revision(self,key):
        return self.c.execute('SELECT r.id,r.content_hash FROM content.question_revisions r JOIN content.questions q ON q.id=r.question_id WHERE q.source_key=%s ORDER BY r.revision_number DESC LIMIT 1',(key,)).fetchone()
    def membership(self):
        t=self.scalar("INSERT INTO identity.tenants(name) VALUES ('test only') RETURNING id")
        u=self.scalar('INSERT INTO identity.users(auth_subject) VALUES (%s) RETURNING id',(str(uuid.uuid4()),))
        m=self.scalar("INSERT INTO identity.memberships(tenant_id,user_id,role) VALUES (%s,%s,'reviewer') RETURNING id",(t,u))
        return t,m
    def publish(self,key):
        r,h=self.revision(key);t,m=self.membership()
        self.c.execute("UPDATE ingestion.content_sources SET rights_status='permitted',rights_evidence_ref='synthetic test fixture only'")
        self.c.execute('UPDATE content.choice_groups g SET rule_reviewed=true,selection_min=1,selection_max=(SELECT count(*) FROM content.choices c WHERE c.group_id=g.id) WHERE revision_id=%s',(r,))
        self.c.execute("UPDATE content.question_media SET reveal_stage='question' WHERE revision_id=%s AND role='original_card'",(r,))
        for aspect in ['prompt','answer_key','explanation','media','groups','rights']:
            self.c.execute('INSERT INTO content.content_reviews(revision_id,reviewer_id,aspect,decision,content_hash,reason) VALUES (%s,%s,%s,%s,%s,%s)',(r,m,aspect,'approved',h,'test only'))
        self.c.execute("UPDATE content.question_revisions SET status='published' WHERE id=%s",(r,))
        return r,t,m

    def test_02_grouped_grading_and_constraints(self):
        r,_=self.revision('qz_1_8')
        self.assertEqual(self.scalar('SELECT count(*) FROM content.choice_groups WHERE revision_id=%s',(r,)),2)
        choices=dict(self.c.execute('SELECT source_choice_number,id FROM content.choices WHERE revision_id=%s',(r,)).fetchall())
        for numbers,expected in [([1,4],True),([4,1],True),([1],False),([1,3,4],False),([1,1,4],False),([],False)]:
            self.assertEqual(self.scalar('SELECT content.exact_set_score(%s,%s)',(r,[choices[n] for n in numbers])),expected)
        other=self.scalar('SELECT id FROM content.choices WHERE revision_id<>%s LIMIT 1',(r,))
        self.fails('INSERT INTO content.answer_keys VALUES (%s,%s)',(r,other))

    def test_03_publication_and_revision_immutability(self):
        r,_=self.revision('qz_1_8')
        self.fails("UPDATE content.question_revisions SET status='published' WHERE id=%s",(r,))
        r,_,_=self.publish('qz_1_8')
        self.fails("UPDATE content.question_localizations SET prompt='overwrite' WHERE revision_id=%s",(r,))
        self.fails('DELETE FROM content.answer_keys WHERE revision_id=%s',(r,))
        self.fails("UPDATE content.question_revisions SET status='draft' WHERE id=%s",(r,))
        self.fails("UPDATE ingestion.source_records SET raw_payload='{}'")

    def test_04_student_boundaries_and_answer_secrecy(self):
        t1,m1=self.membership();t2,m2=self.membership()
        for t,m in [(t1,m1),(t2,m2)]:
            self.c.execute("INSERT INTO learning.learning_events(tenant_id,membership_id,event_type,occurred_at,payload,dedupe_key) VALUES (%s,%s,'test',now(),'{}',%s)",(t,m,uuid.uuid4()))
        self.fails("INSERT INTO learning.attempts(tenant_id,membership_id,mode) VALUES (%s,%s,'practice')",(t1,m2))
        self.c.execute('GRANT INSERT ON learning.learning_events TO sya9a_student_runtime')
        self.c.execute('SET LOCAL ROLE sya9a_student_runtime')
        self.assertEqual(self.scalar('SELECT count(*) FROM learning.learning_events'),0)
        self.c.execute("SELECT set_config('app.tenant_id',%s,true),set_config('app.membership_id',%s,true)",(str(t1),str(m1)))
        self.assertEqual(self.scalar('SELECT count(*) FROM learning.learning_events'),1)
        self.fails("INSERT INTO learning.learning_events(tenant_id,membership_id,event_type,occurred_at,payload,dedupe_key) VALUES (%s,%s,'bad',now(),'{}',%s)",(t2,m2,uuid.uuid4()))
        self.fails('SELECT * FROM content.answer_keys')
        self.fails('SELECT * FROM ingestion.source_records')
        self.c.execute('RESET ROLE')

    def test_05_response_revision_boundary_and_freeze(self):
        r,t,m=self.publish('qz_1_8')
        a=self.scalar("INSERT INTO learning.attempts(tenant_id,membership_id,mode,state) VALUES (%s,%s,'practice','in_progress') RETURNING id",(t,m))
        ids=[row[0] for row in self.c.execute('SELECT id FROM content.choices WHERE revision_id=%s ORDER BY display_position',(r,))]
        i=self.scalar("INSERT INTO learning.attempt_items(tenant_id,membership_id,attempt_id,position,question_revision_id,locale,media_manifest,displayed_choice_order) VALUES (%s,%s,%s,1,%s,'ary-MA','{}',%s) RETURNING id",(t,m,a,r,ids))
        key=uuid.uuid4()
        response=self.scalar('INSERT INTO learning.responses(tenant_id,membership_id,attempt_item_id,question_revision_id,response_revision,idempotency_key) VALUES (%s,%s,%s,%s,1,%s) RETURNING id',(t,m,i,r,key))
        other=self.scalar('SELECT id FROM content.choices WHERE revision_id<>%s LIMIT 1',(r,))
        self.fails('INSERT INTO learning.response_choices VALUES (%s,%s,%s,%s,%s)',(response,r,t,m,other))
        self.c.execute('INSERT INTO learning.response_choices VALUES (%s,%s,%s,%s,%s)',(response,r,t,m,ids[0]))
        self.fails('INSERT INTO learning.responses(tenant_id,membership_id,attempt_item_id,question_revision_id,response_revision,idempotency_key) VALUES (%s,%s,%s,%s,2,%s)',(t,m,i,r,key))
        self.c.execute("UPDATE learning.attempts SET state='submitted' WHERE id=%s",(a,))
        self.fails('INSERT INTO learning.response_choices VALUES (%s,%s,%s,%s,%s)',(response,r,t,m,ids[1]))
        self.fails("UPDATE learning.attempts SET state='in_progress' WHERE id=%s",(a,))

    def test_06_modified_import_preserves_history(self):
        old=self.revision('qz_1_1')[0]
        original=self.scalar('SELECT prompt FROM content.question_localizations WHERE revision_id=%s',(old,))
        raw=json.loads((self.source/'questions.json').read_text())
        raw[0]['question']+=' [test revision]'
        (self.source/'questions.json').write_text(json.dumps(raw,ensure_ascii=False))
        self.assertEqual(run(self.source,self.content)['status'],'imported')
        self.assertNotEqual(self.revision('qz_1_1')[0],old)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.questions'),400)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.question_revisions'),401)
        self.assertEqual(self.scalar('SELECT prompt FROM content.question_localizations WHERE revision_id=%s',(old,)),original)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.assessment_revisions'),11)
        self.assertEqual(run(self.source,self.content)['status'],'already_imported')

    def test_07_changed_image_at_same_url_is_versioned(self):
        old=self.revision('qz_1_2')[0]
        old_asset=self.scalar("SELECT asset_id FROM content.question_media WHERE revision_id=%s AND role='original_card'",(old,))
        image=self.source/'images/serie_1/q_2.jpg'
        image.write_bytes(image.read_bytes()+b'changed-test-bytes')
        self.assertEqual(run(self.source,self.content)['status'],'imported')
        new=self.revision('qz_1_2')[0]
        new_asset=self.scalar("SELECT asset_id FROM content.question_media WHERE revision_id=%s AND role='original_card'",(new,))
        self.assertNotEqual(old,new)
        self.assertNotEqual(old_asset,new_asset)
        self.assertEqual(self.scalar("SELECT asset_id FROM content.question_media WHERE revision_id=%s AND role='original_card'",(old,)),old_asset)
        self.fails("UPDATE content.media_assets SET object_key='overwrite' WHERE id=%s",(old_asset,))

    def test_08_local_audio_mapping_and_metadata(self):
        self.assertEqual(self.scalar("SELECT count(*) FROM content.media_assets WHERE mime='audio/mpeg' AND availability='local' AND duration_seconds>0"),self.expected_audio_assets)
        for qid in ['qz_1_1','qz_5_20','qz_10_40']:
            revision=self.revision(qid)[0]
            row=self.c.execute("SELECT a.object_key,a.duration_seconds FROM content.question_media m JOIN content.media_assets a ON a.id=m.asset_id WHERE m.revision_id=%s AND m.role='audio'",(revision,)).fetchone()
            _,serie,question=qid.split('_')
            self.assertTrue(row[0].endswith(f'/audio/serie_{serie}/q_{question}.mp3'))
            self.assertGreater(row[1],0)

    def test_09_invalid_or_misassigned_audio_is_rejected(self):
        raw_file=self.source/'questions.json'
        original=raw_file.read_bytes()
        raw=json.loads(original)
        try:
            raw[0]['localAudioPath']='../outside.mp3'
            raw_file.write_text(json.dumps(raw))
            with self.assertRaises(ValueError): run(self.source,self.content,dry_run=True)
            raw[0]['localAudioPath']='audio/serie_1/q_2.mp3'
            raw_file.write_text(json.dumps(raw))
            with self.assertRaises(ValueError): run(self.source,self.content,dry_run=True)
        finally: raw_file.write_bytes(original)
        audio=self.source/'audio/serie_1/q_1.mp3'
        original_audio=audio.read_bytes()
        try:
            audio.write_bytes(b'not an mp3')
            with self.assertRaises(Exception): run(self.source,self.content,dry_run=True)
        finally: audio.write_bytes(original_audio)

    def test_10_changed_audio_creates_new_revision(self):
        old=self.revision('qz_1_3')[0]
        old_asset=self.scalar("SELECT asset_id FROM content.question_media WHERE revision_id=%s AND role='audio'",(old,))
        (self.source/'audio/serie_1/q_3.mp3').write_bytes((self.source/'audio/serie_1/q_4.mp3').read_bytes())
        self.assertEqual(run(self.source,self.content)['status'],'imported')
        new=self.revision('qz_1_3')[0]
        new_asset=self.scalar("SELECT asset_id FROM content.question_media WHERE revision_id=%s AND role='audio'",(new,))
        self.assertNotEqual(old,new)
        self.assertNotEqual(old_asset,new_asset)
        self.assertEqual(self.scalar("SELECT asset_id FROM content.question_media WHERE revision_id=%s AND role='audio'",(old,)),old_asset)

if __name__=='__main__': unittest.main(verbosity=2)
