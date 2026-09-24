"""Private CLI for publication blockers and attributable content decisions.

Export is read-only; record defaults to dry-run. This tool never invents a
reviewer, edits source content, grants rights, or publishes a question.
"""
import argparse
import json
from pathlib import Path
from uuid import UUID
from psycopg.rows import dict_row
from import_dataset import connect
from prepare_training_review import fetch_packet
from build_training_editorial import fingerprint

ASPECTS=('prompt','answer_key','explanation','media','groups','rights')


def snapshot(c, series_id=None):
    packet=fetch_packet(c,series_id)
    for item in packet['items']:
        rid=item['revision_id']
        item['concept_links']=c.execute('''SELECT k.code,q.weight,q.approval_status FROM content.question_concepts q
          JOIN content.concepts k ON k.id=q.concept_id WHERE q.revision_id=%s ORDER BY k.code''',(rid,)).fetchall()
        item['rights_evidence_ref']=c.execute('''SELECT s.rights_evidence_ref FROM content.question_revisions r
          JOIN content.questions q ON q.id=r.question_id JOIN ingestion.content_sources s ON s.id=q.source_id
          WHERE r.id=%s''',(rid,)).fetchone()['rights_evidence_ref']
        item['fingerprint']=fingerprint(item)
    return packet


def blockers(c,item):
    rid=item['revision_id'];reasons=[]
    if item['status']!='draft':reasons.append('not_draft')
    if not item['prompt'].strip() or item['needs_prompt_reconstruction']:reasons.append('prompt_incomplete')
    if not item['explanation'].strip():reasons.append('explanation_missing')
    if item['rights_status']!='permitted' or not (item['rights_evidence_ref'] or '').strip():reasons.append('source_permission_missing')
    if not item['concept_links'] or any(x['approval_status']!='approved' for x in item['concept_links']):reasons.append('concept_review_missing')
    groups=c.execute('''SELECT g.id,g.selection_min,g.selection_max,g.rule_reviewed,
      (SELECT count(*) FROM content.choices ch WHERE ch.group_id=g.id) AS choices,
      (SELECT count(*) FROM content.answer_keys k JOIN content.choices ch ON ch.id=k.choice_id WHERE ch.group_id=g.id) AS answers
      FROM content.choice_groups g WHERE g.revision_id=%s''',(rid,)).fetchall()
    if not groups or any(not g['rule_reviewed'] or g['selection_min'] is None or g['selection_max'] is None or
        not 0<=g['selection_min']<=g['answers']<=g['selection_max']<=g['choices'] for g in groups):reasons.append('choice_bounds_unreviewed')
    if len(item['choices'])<2 or not item['source_answer_numbers']:reasons.append('answer_set_missing')
    if not c.execute("""SELECT 1 FROM content.question_media m JOIN content.media_assets a ON a.id=m.asset_id
      WHERE m.revision_id=%s AND m.role IN ('original_card','scene') AND m.reveal_stage='question' AND a.availability='local'""",(rid,)).fetchone():reasons.append('question_media_unreviewed')
    reviews=c.execute('''SELECT r.aspect,r.decision,r.content_hash,m.role,m.status,t.status AS tenant_status
      FROM content.content_reviews r JOIN identity.memberships m ON m.id=r.reviewer_id
      JOIN identity.tenants t ON t.id=m.tenant_id WHERE r.revision_id=%s AND NOT r.superseded''',(rid,)).fetchall()
    for aspect in ASPECTS:
        if not any(r['aspect']==aspect and r['decision']=='approved' and r['content_hash']==item['content_hash']
          and r['role'] in ('reviewer','admin') and r['status']=='active' and r['tenant_status']=='active' for r in reviews):
            reasons.append('approval_missing:'+aspect)
    if any(r['decision']=='rejected' for r in reviews):reasons.append('unresolved_rejection')
    return reasons


def export(c,output):
    packet=snapshot(c);items=[]
    for i in packet['items']:
        items.append({'revision_id':str(i['revision_id']),'source_key':i['source_key'],
          'expected_fingerprint':i['fingerprint'],'blockers':blockers(c,i),
          'decisions':[{'aspect':a,'decision':'pending','reason':'','evidence_refs':[]} for a in ASPECTS]})
    report={'version':'content-decisions-v1','series_id':str(packet['series']['id']),
      'notice':'A template, not approval. Supply an existing reviewer only after their actual review.', 'items':items}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'questions':len(items),'without_blockers':sum(not i['blockers'] for i in items)}


def record(c,document,reviewer_id,apply=False):
    c.row_factory=dict_row
    if document.get('version')!='content-decisions-v1' or not document.get('items'):raise ValueError('Invalid decision document')
    UUID(str(reviewer_id));UUID(document['series_id'])
    reviewer=c.execute('''SELECT m.id FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id
      WHERE m.id=%s AND m.role IN ('reviewer','admin') AND m.status='active' AND t.status='active' FOR SHARE OF m,t''',(reviewer_id,)).fetchone()
    if not reviewer:raise ValueError('An existing active reviewer/admin membership is required')
    ids=[str(UUID(i['revision_id'])) for i in document['items']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate revision')
    c.execute('SELECT id FROM content.question_revisions WHERE id=ANY(%s::uuid[]) ORDER BY id FOR UPDATE',(ids,)).fetchall()
    current={str(i['revision_id']):i for i in snapshot(c,document['series_id'])['items']}
    commands=[]
    for item in document['items']:
        base=current.get(item['revision_id'])
        if not base or base['status']!='draft' or item['expected_fingerprint']!=base['fingerprint']:raise ValueError('Stale or non-draft review target')
        aspects=set()
        for d in item['decisions']:
            if d['aspect'] not in ASPECTS or d['aspect'] in aspects:raise ValueError('Invalid or duplicate aspect')
            aspects.add(d['aspect'])
            if d['decision']=='pending':continue
            if d['decision'] not in ('approved','rejected'):raise ValueError('Invalid decision')
            if not isinstance(d.get('reason'),str) or not d['reason'].strip():raise ValueError('A review reason is required')
            refs=d.get('evidence_refs')
            if not isinstance(refs,list) or not refs or any(not isinstance(v,str) or not v.strip() for v in refs):raise ValueError('Evidence references required')
            reason=json.dumps({'reason':d['reason'],'evidence_refs':refs,'snapshot':base['fingerprint'],'format':'content-decisions-v1'},ensure_ascii=False,sort_keys=True)
            commands.append((base,d,reason))
    if not commands:raise ValueError('No completed decisions; the pending template is not a review')
    written=0
    if apply:
        for base,d,reason in commands:
            old=c.execute('''SELECT reviewer_id,decision,content_hash,reason FROM content.content_reviews
              WHERE revision_id=%s AND aspect=%s AND NOT superseded''',(base['revision_id'],d['aspect'])).fetchall()
            if len(old)==1 and str(old[0]['reviewer_id'])==str(reviewer_id) and old[0]['decision']==d['decision'] and old[0]['content_hash']==base['content_hash'] and old[0]['reason']==reason:continue
            c.execute('UPDATE content.content_reviews SET superseded=true WHERE revision_id=%s AND aspect=%s AND NOT superseded',(base['revision_id'],d['aspect']))
            c.execute('''INSERT INTO content.content_reviews(revision_id,reviewer_id,aspect,decision,content_hash,reason)
              VALUES(%s,%s,%s,%s,%s,%s)''',(base['revision_id'],reviewer_id,d['aspect'],d['decision'],base['content_hash'],reason));written+=1
    return {'validated_decisions':len(commands),'written':written,'applied':apply,'published':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('export');p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('record');p.add_argument('--file',type=Path,required=True);p.add_argument('--reviewer-id',required=True);p.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with connect() as c:
        result=export(c,args.output) if args.action=='export' else record(c,json.loads(args.file.read_text(encoding='utf-8-sig')),args.reviewer_id,args.apply)
    print(json.dumps(result))
