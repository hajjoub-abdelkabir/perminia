"""Artificial, non-driving questions used only in disposable test databases."""
import hashlib
from uuid import uuid4
def install(c):
    def one(sql,args=()):return c.execute(sql,args).fetchone()[0]
    source=one("INSERT INTO ingestion.content_sources(name,base_url,rights_status,rights_evidence_ref) VALUES(%s,'https://example.test','permitted','synthetic fixture only') RETURNING id",('training-test-'+str(uuid4()),))
    batch=one("INSERT INTO ingestion.import_batches(source_id,input_sha256,importer_version,enrichment_script_sha256,archive_key,status) VALUES(%s,'test','test','test','test','complete') RETURNING id",(source,))
    tenant=one("INSERT INTO identity.tenants(name) VALUES('synthetic reviewer') RETURNING id")
    user=one('INSERT INTO identity.users(auth_subject) VALUES(%s) RETURNING id',('fixture-'+str(uuid4()),))
    reviewer=one("INSERT INTO identity.memberships(tenant_id,user_id,role) VALUES(%s,%s,'reviewer') RETURNING id",(tenant,user))
    c.execute("INSERT INTO content.topics(id,label) VALUES('test-topic','موضوع تقني اختباري') ON CONFLICT DO NOTHING")
    concept=one("INSERT INTO content.concepts(topic_id,code,label) VALUES('test-topic',%s,'مفهوم اختباري') RETURNING id",(str(uuid4()),))
    family=one("INSERT INTO content.duplicate_families(note) VALUES('synthetic same family') RETURNING id")
    series=one("INSERT INTO content.assessments(source_id,source_key,kind,title) VALUES(%s,'synthetic','source_series','سلسلة تقنية للاختبار') RETURNING id",(source,))
    ar=one("INSERT INTO content.assessment_revisions(assessment_id,revision_number,item_count,pool_manifest_hash) VALUES(%s,1,8,'test') RETURNING id",(series,))
    revisions=[];keys=[]
    for n in range(8):
        record=one("INSERT INTO ingestion.source_records(batch_id,source_key,source_series_key,source_position,source_url,raw_payload,raw_sha256) VALUES(%s,%s,'synthetic',%s,'https://example.test','{}','test') RETURNING id",(batch,str(n),n+1))
        q=one("INSERT INTO content.questions(source_id,source_key,category_id,duplicate_family_id) VALUES(%s,%s,'B',%s) RETURNING id",(source,str(n),family if n<2 else None))
        h=hashlib.sha256(str(q).encode()).hexdigest()
        r=one("INSERT INTO content.question_revisions(question_id,revision_number,response_type,content_hash,source_record_id) VALUES(%s,1,'single',%s,%s) RETURNING id",(q,h,record));revisions.append(r)
        c.execute("INSERT INTO content.question_localizations VALUES(%s,'ary-MA','سؤال تقني فقط','شرح اصطناعي للاختبار، ليس قانون السير')",(r,))
        g=one("INSERT INTO content.choice_groups(revision_id,position,selection_min,selection_max,rule_reviewed) VALUES(%s,1,1,1,true) RETURNING id",(r,))
        for k in (1,2):
            choice=one('INSERT INTO content.choices(revision_id,group_id,source_choice_number,display_position) VALUES(%s,%s,%s,%s) RETURNING id',(r,g,k,k))
            c.execute("INSERT INTO content.choice_localizations VALUES(%s,'ary-MA',%s)",(choice,'اختيار '+str(k)))
            if k==1:c.execute('INSERT INTO content.answer_keys VALUES(%s,%s)',(r,choice));keys.append(choice)
        asset=one("INSERT INTO content.media_assets(source_id,sha256,object_key,original_url,mime,byte_size,availability) VALUES(%s,%s,%s,%s,'image/png',1,'local') RETURNING id",(source,str(uuid4()),'test/'+str(uuid4()),'https://example.test/'+str(uuid4())))
        c.execute("INSERT INTO content.question_media(revision_id,asset_id,role,locale,position,reveal_stage) VALUES(%s,%s,'original_card','ary-MA',1,'question')",(r,asset))
        c.execute("INSERT INTO content.question_concepts(revision_id,concept_id,weight,approval_status) VALUES(%s,%s,1,'approved')",(r,concept))
        if n<7:
            for aspect in ('prompt','answer_key','explanation','media','groups','rights'):
                c.execute("INSERT INTO content.content_reviews(revision_id,reviewer_id,aspect,decision,content_hash,reason) VALUES(%s,%s,%s,'approved',%s,'synthetic test only')",(r,reviewer,aspect,h))
            c.execute("UPDATE content.question_revisions SET status='published' WHERE id=%s",(r,))
        c.execute('INSERT INTO content.assessment_items VALUES(%s,%s,%s,%s)',(ar,n+1,r,q))
    return {'series':series,'revisions':revisions,'keys':keys}
