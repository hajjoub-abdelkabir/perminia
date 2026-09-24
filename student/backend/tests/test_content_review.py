import copy
import unittest
from uuid import uuid4
from test_training_editorial import EditorialTests as Base
from content_review import snapshot,blockers,record,ASPECTS


class ReviewTests(unittest.TestCase):
    setUpClass=classmethod(Base.setUpClass.__func__)
    cleanup=classmethod(Base.cleanup.__func__)
    setUp=Base.setUp
    scalar=Base.scalar

    def document(self):
        item=snapshot(self.c,self.fixture['series'])['items'][-1]
        return {'version':'content-decisions-v1','series_id':str(self.fixture['series']),'items':[
          {'revision_id':str(item['revision_id']),'expected_fingerprint':item['fingerprint'],
           'decisions':[{'aspect':'prompt','decision':'approved','reason':'Synthetic test review only','evidence_refs':['test fixture']}]}]}

    def reviewer(self):return self.scalar('SELECT reviewer_id FROM content.content_reviews LIMIT 1')

    def test_dry_run_and_idempotent_record_without_publication(self):
        d=self.document();r=self.reviewer()
        self.assertEqual(record(self.c,d,r)['written'],0)
        self.assertEqual(record(self.c,d,r,True)['written'],1)
        self.assertEqual(record(self.c,d,r,True)['written'],0)
        self.assertEqual(self.scalar('SELECT status FROM content.question_revisions WHERE id=%s',(self.item['revision_id'],)),'draft')

    def test_missing_reviewer_rejected(self):
        with self.assertRaisesRegex(ValueError,'existing active'):record(self.c,self.document(),uuid4(),True)

    def test_inactive_reviewer_rejected(self):
        r=self.reviewer();self.c.execute("UPDATE identity.memberships SET status='inactive' WHERE id=%s",(r,))
        with self.assertRaisesRegex(ValueError,'existing active'):record(self.c,self.document(),r,True)

    def test_content_changes_invalidate_document(self):
        d=self.document();self.c.execute("UPDATE content.question_localizations SET explanation='changed' WHERE revision_id=%s",(self.item['revision_id'],))
        with self.assertRaisesRegex(ValueError,'Stale'):record(self.c,d,self.reviewer(),True)

    def test_pending_is_not_approval(self):
        d=self.document();d['items'][0]['decisions'][0]['decision']='pending'
        with self.assertRaisesRegex(ValueError,'No completed'):record(self.c,d,self.reviewer(),True)

    def test_missing_evidence_and_duplicate_aspect_rejected_before_write(self):
        d=self.document();d['items'][0]['decisions'][0]['evidence_refs']=[]
        with self.assertRaisesRegex(ValueError,'Evidence'):record(self.c,d,self.reviewer(),True)
        d=self.document();d['items'][0]['decisions']*=2
        with self.assertRaisesRegex(ValueError,'duplicate aspect'):record(self.c,d,self.reviewer(),True)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.content_reviews WHERE revision_id=%s',(self.item['revision_id'],)),0)

    def test_rejection_history_preserved_when_replaced(self):
        d=self.document();r=self.reviewer();d['items'][0]['decisions'][0]['decision']='rejected'
        record(self.c,d,r,True)
        d['items'][0]['decisions'][0]['decision']='approved';record(self.c,d,r,True)
        self.assertEqual(self.scalar('SELECT count(*) FROM content.content_reviews WHERE revision_id=%s',(self.item['revision_id'],)),2)
        self.assertEqual(self.scalar("SELECT count(*) FROM content.content_reviews WHERE revision_id=%s AND decision='rejected' AND superseded",(self.item['revision_id'],)),1)

    def test_blockers_require_concepts_and_six_reviews(self):
        item=snapshot(self.c,self.fixture['series'])['items'][-1]
        b=blockers(self.c,item)
        self.assertIn('concept_review_missing',b)
        for a in ASPECTS:self.assertIn('approval_missing:'+a,b)


if __name__=='__main__':unittest.main()
