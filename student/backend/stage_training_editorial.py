"""Stage pending concepts and provenance; never changes keys or publishes.

Default is validation only. --apply performs one atomic, idempotent transaction.
Conflicts with any existing review or annotation require explicit reconciliation.
"""
import argparse
import json
import re
from pathlib import Path
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from import_dataset import connect
from prepare_training_review import fetch_packet
from build_training_editorial import VERSION, fingerprint


def validate(proposals):
    if proposals.get('version')!=VERSION:raise ValueError('Unknown proposal version')
    concepts=proposals.get('concepts',[]);candidates=proposals.get('candidates',[])
    if not concepts or not candidates or len(candidates)>400:raise ValueError('Empty or excessive proposal set')
    codes=set()
    for c in concepts:
        code=c['code']
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{1,79}',code) or code in codes:raise ValueError('Duplicate or invalid concept code')
        if not isinstance(c['label'],str) or not c['label'].strip() or len(c['label'])>200:raise ValueError('Invalid label')
        codes.add(code)
    ids=set()
    for p in candidates:
        if p['revision_id'] in ids:raise ValueError('Duplicate revision')
        ids.add(p['revision_id'])
        if p.get('state')!='pending':raise ValueError('Only pending proposals can be staged')
        if len(p.get('concept_codes',[]))!=1 or p['concept_codes'][0] not in codes:raise ValueError('Exactly one known primary concept required')
        if not re.fullmatch('[a-f0-9]{64}',p['base_fingerprint']):raise ValueError('Invalid fingerprint')


def stage(c, proposals, apply=False):
    validate(proposals);c.row_factory=dict_row
    # Serializes independent editors using this importer. Parent locks also
    # serialize content-child edits/publication through existing DB triggers.
    c.execute("SELECT pg_advisory_xact_lock(hashtext('training-editorial-v1'))")
    ids=[p['revision_id'] for p in proposals['candidates']]
    rows=c.execute('SELECT id,source_record_id,status FROM content.question_revisions WHERE id=ANY(%s::uuid[]) ORDER BY id FOR UPDATE',(ids,)).fetchall()
    revisions={str(r['id']):r for r in rows}
    current={str(i['revision_id']):i for i in fetch_packet(c,proposals['series_id'])['items']}
    for p in proposals['candidates']:
        rid=p['revision_id'];r=revisions.get(rid);item=current.get(rid)
        if not r or not item or r['status']!='draft':raise ValueError('Proposal must match a current draft in the selected series')
        if item['source_key']!=p['source_key'] or fingerprint(item)!=p['base_fingerprint'] or item['content_hash']!=p['base_content_hash']:
            raise ValueError('Stale content snapshot; re-export and reconcile the proposal')
        if c.execute('SELECT 1 FROM content.content_reviews WHERE revision_id=%s LIMIT 1',(rid,)).fetchone():
            raise ValueError('Reviewed content needs a separate editorial workflow')
        existing=c.execute('SELECT value,review_status FROM ingestion.enrichment_candidates WHERE source_record_id=%s AND field_name=%s',(r['source_record_id'],VERSION)).fetchone()
        if existing and (existing['review_status']!='pending' or existing['value']!=p):
            raise ValueError('Existing proposal differs; do not overwrite editorial work')
        links=c.execute('SELECT k.code,q.weight,q.approval_status FROM content.question_concepts q JOIN content.concepts k ON k.id=q.concept_id WHERE q.revision_id=%s',(rid,)).fetchall()
        if links and (len(links)!=1 or links[0]['code']!=p['concept_codes'][0] or links[0]['approval_status']!='pending' or links[0]['weight']!=1):
            raise ValueError('Existing concept links conflict with proposal')
    for concept in proposals['concepts']:
        if not c.execute('SELECT 1 FROM content.topics WHERE id=%s',(concept['topic_id'],)).fetchone():raise ValueError('Unknown topic')
        existing=c.execute('SELECT topic_id,label FROM content.concepts WHERE code=%s',(concept['code'],)).fetchone()
        if existing and (existing['topic_id']!=concept['topic_id'] or existing['label']!=concept['label']):raise ValueError('Concept definition conflict')
    if apply:
        for concept in proposals['concepts']:
            c.execute('INSERT INTO content.concepts(code,topic_id,label) VALUES(%s,%s,%s) ON CONFLICT(code) DO NOTHING',(concept['code'],concept['topic_id'],concept['label']))
        for p in proposals['candidates']:
            rid=p['revision_id'];record=revisions[rid]['source_record_id']
            c.execute("INSERT INTO ingestion.enrichment_candidates(source_record_id,field_name,value,producer_kind,producer_version) VALUES(%s,%s,%s,'model',%s) ON CONFLICT(source_record_id,field_name) DO NOTHING",(record,VERSION,Jsonb(p),VERSION))
            # Skip existing identical rows rather than firing the content-edit
            # trigger again. No approved links or family IDs are written here.
            c.execute("""INSERT INTO content.question_concepts(revision_id,concept_id,weight,approval_status)
              SELECT %s,id,1,'pending' FROM content.concepts WHERE code=%s
              AND NOT EXISTS(SELECT 1 FROM content.question_concepts WHERE revision_id=%s AND concept_id=content.concepts.id)""",(rid,p['concept_codes'][0],rid))
    return {'validated':len(ids),'applied':apply,'concepts':len(proposals['concepts']),'approval_status':'pending','published':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--proposals',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();proposals=json.loads(args.proposals.read_text(encoding='utf-8-sig'))
    with connect() as c:report=stage(c,proposals,args.apply)
    print(json.dumps(report))
