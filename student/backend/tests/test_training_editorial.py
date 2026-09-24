"""Editorial staging tests use a disposable database, never the real bank."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from psycopg import sql
from psycopg.rows import tuple_row
import test_accounts as accounts
from training_fixture import install
from prepare_training_review import fetch_packet
from stage_training_editorial import stage, validate
from build_training_editorial import VERSION, fingerprint, build


class EditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database='sya9a_student_test_editorial_'+uuid4().hex[:12]
        with accounts.owner_connect() as c:
            c.autocommit=True
            c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.database)))
        cls.addClassCleanup(cls.cleanup)
        subprocess.run(['alembic','upgrade','head'],env=dict(os.environ,POSTGRES_DB=cls.database),check=True)
        with accounts.owner_connect(cls.database) as c:
            cls.fixture=install(c)
            c.execute('DELETE FROM content.question_concepts WHERE revision_id=%s',(cls.fixture['revisions'][-1],))

    @classmethod
    def cleanup(cls):
        assert cls.database.startswith('sya9a_student_test_editorial_')
        with accounts.owner_connect() as c:
            c.autocommit=True
            c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.database)))

    def setUp(self):
        self.c=accounts.owner_connect(self.database)
        self.addCleanup(self.c.close);self.addCleanup(self.c.rollback)
        packet=fetch_packet(self.c,self.fixture['series']);item=packet['items'][-1]
        self.item=item
        self.p={'version':VERSION,'series_id':str(self.fixture['series']),
            'concepts':[{'code':'editorial.test','topic_id':'test-topic','label':'مفهوم مقترح اختباري'}],
            'candidates':[{'revision_id':str(item['revision_id']),'source_key':item['source_key'],
                'base_fingerprint':fingerprint(item),'base_content_hash':item['content_hash'],
                'concept_codes':['editorial.test'],'state':'pending','family_candidate':'test-family'}]}

    def scalar(self, query, args=()):
        with self.c.cursor(row_factory=tuple_row) as cur:return cur.execute(query,args).fetchone()[0]

    def test_dry_run_does_not_write(self):
        self.assertFalse(stage(self.c,self.p)['applied'])
        self.assertEqual(self.scalar("SELECT count(*) FROM content.concepts WHERE code='editorial.test'"),0)

    def test_apply_is_pending_idempotent_and_preserves_keys(self):
        keys=self.scalar('SELECT count(*) FROM content.answer_keys')
        reviews=self.scalar('SELECT count(*) FROM content.content_reviews')
        stage(self.c,self.p,True);stage(self.c,self.p,True)
        self.assertEqual(self.scalar("SELECT count(*) FROM ingestion.enrichment_candidates WHERE field_name=%s",(VERSION,)),1)
        self.assertEqual(self.scalar("SELECT approval_status FROM content.question_concepts WHERE revision_id=%s",(self.item['revision_id'],)),'pending')
        self.assertEqual(self.scalar('SELECT status FROM content.question_revisions WHERE id=%s',(self.item['revision_id'],)),'draft')
        self.assertEqual(self.scalar('SELECT count(*) FROM content.answer_keys'),keys)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.content_reviews'),reviews)
        self.assertEqual(self.scalar('SELECT duplicate_family_id FROM content.questions WHERE id=(SELECT question_id FROM content.question_revisions WHERE id=%s)',(self.item['revision_id'],)),None)

    def test_text_edit_detected_even_with_same_importer_hash(self):
        self.c.execute("UPDATE content.question_localizations SET prompt='تغيير بعد التصدير' WHERE revision_id=%s",(self.item['revision_id'],))
        with self.assertRaisesRegex(ValueError,'Stale'):stage(self.c,self.p,True)

    def test_published_question_rejected(self):
        published=fetch_packet(self.c,self.fixture['series'])['items'][0]
        self.p['candidates'][0].update(revision_id=str(published['revision_id']),source_key=published['source_key'],base_fingerprint=fingerprint(published),base_content_hash=published['content_hash'])
        with self.assertRaisesRegex(ValueError,'current draft'):stage(self.c,self.p,True)

    def test_existing_proposal_cannot_be_overwritten(self):
        stage(self.c,self.p,True)
        self.p['candidates'][0]['family_candidate']='changed'
        with self.assertRaisesRegex(ValueError,'Existing proposal'):stage(self.c,self.p,True)

    def test_reviewed_draft_cannot_be_changed(self):
        reviewer=self.scalar('SELECT reviewer_id FROM content.content_reviews LIMIT 1')
        self.c.execute("INSERT INTO content.content_reviews(revision_id,reviewer_id,aspect,decision,content_hash,reason) VALUES(%s,%s,'prompt','approved',%s,'test only')",(self.item['revision_id'],reviewer,self.item['content_hash']))
        with self.assertRaisesRegex(ValueError,'Reviewed content'):stage(self.c,self.p,True)
        self.assertFalse(self.scalar('SELECT superseded FROM content.content_reviews WHERE revision_id=%s',(self.item['revision_id'],)))

    def test_duplicate_and_approval_flags_rejected(self):
        p=copy.deepcopy(self.p);p['candidates']*=2
        with self.assertRaisesRegex(ValueError,'Duplicate revision'):validate(p)
        self.p['candidates'][0]['state']='approved'
        with self.assertRaisesRegex(ValueError,'Only pending'):validate(self.p)

    def test_wrong_series_rejected(self):
        self.p['series_id']=str(uuid4())
        with self.assertRaises(ValueError):stage(self.c,self.p,True)

    def test_all_validation_happens_before_writing(self):
        self.p['concepts'].append({'code':'editorial.missing','topic_id':'absent','label':'غائب'})
        with self.assertRaisesRegex(ValueError,'Unknown topic'):stage(self.c,self.p,True)
        self.assertEqual(self.scalar("SELECT count(*) FROM content.concepts WHERE code='editorial.test'"),0)


class ProposalTests(unittest.TestCase):
    def test_full_curated_coverage_and_reversed_pedestrian_choices(self):
        # Numbers are kept in source snapshots, never inferred by this builder.
        packet={'series':{'id':'test'},'items':[{'source_key':f'qz_1_{n}','position':n,'revision_id':str(n),'content_hash':'test','source_answer_numbers':[2 if n==36 else 1]} for n in range(1,41)]}
        p=build(packet)
        self.assertEqual(len(p['candidates']),40);self.assertEqual(len(p['concepts']),26)
        self.assertEqual(sum(x['priority']=='high' for x in p['candidates']),6)
        self.assertEqual(p['candidates'][10]['family_candidate'],p['candidates'][35]['family_candidate'])
        self.assertTrue(all(x['state']=='pending' for x in p['candidates']))
        self.assertEqual(packet['items'][35]['source_answer_numbers'],[2])
        self.assertEqual(packet['items'][10]['source_answer_numbers'],[1])

    def test_wrong_bank_is_not_positionally_mapped(self):
        with self.assertRaises(ValueError):build({'series':{},'items':[]})


if __name__=='__main__':unittest.main()
