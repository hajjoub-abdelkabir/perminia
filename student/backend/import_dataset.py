"""Deterministic, transaction-safe import. Never executes source scripts or SQL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from audio_metadata import probe_audio

VERSION = 'permis-import-v2-audio'
NS = uuid.UUID('756b852c-90e1-46bb-b1f3-fa2456346883')
def uid(*parts): return uuid.uuid5(NS, '|'.join(map(str,parts)))
def digest(data): return hashlib.sha256(data).hexdigest()
def packed(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def connect():
    return psycopg.connect(host=os.environ.get('POSTGRES_HOST','db'),dbname=os.environ['POSTGRES_DB'],user=os.environ['POSTGRES_USER'],password=os.environ['POSTGRES_PASSWORD'])
def insert(c, table, **values):
    query=sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING').format(sql.Identifier(*table.split('.')),sql.SQL(',').join(map(sql.Identifier,values)),sql.SQL(',').join(sql.Placeholder() for _ in values))
    c.execute(query,[Jsonb(v) if isinstance(v,(dict,list)) else v for v in values.values()])

def validate(root):
    raw=json.loads((root/'questions.json').read_text(encoding='utf-8-sig'))
    enriched=json.loads((root/'questions_ai_annotated.json').read_text(encoding='utf-8-sig'))
    by_id={q['id']:q for q in enriched}
    if len(by_id)!=len(enriched) or len({q['key'] for q in raw})!=len(raw) or set(by_id)!={q['key'] for q in raw}: raise ValueError('Duplicate or mismatched source IDs')
    manifest={}
    for f in sorted(root.rglob('*')):
        if f.is_file(): manifest[f.relative_to(root).as_posix()]=digest(f.read_bytes())
    positions=set()
    for q in raw:
        pair=(q['serieId'],q['questionId'])
        if pair in positions or min(pair)<1: raise ValueError('Invalid series position')
        positions.add(pair)
        options=[o for g in q['options'] for o in g['options']]
        correct=q['correctAnswers']
        if len(options)<2 or any(not isinstance(o,str) or not o.strip() for o in options) or not correct or len(set(correct))!=len(correct) or any(type(n) is not int or not 1<=n<=len(options) for n in correct): raise ValueError(f'Invalid choices: {q["key"]}')
        a=by_id[q['key']]
        if a['serie_id']!=q['serieId'] or a['question_number']!=q['questionId'] or [x['choice_number'] for x in a['choices']]!=list(range(1,len(options)+1)) or sorted(a['correct_choice_numbers'])!=sorted(correct) or sorted(x['choice_number'] for x in a['choices'] if x['is_correct'])!=sorted(correct): raise ValueError('Enrichment answer/identity mismatch')
        for field in ('localImagePath','localImageAltPath','localAudioPath'):
            if not q.get(field): continue
            f=(root/q[field]).resolve()
            if not f.is_relative_to(root.resolve()) or not f.is_file(): raise ValueError('Invalid media path')
            if field=='localAudioPath':
                if q[field]!=f"audio/serie_{q['serieId']}/q_{q['questionId']}.mp3": raise ValueError('Audio series/question filename mismatch')
                if not q.get('audioUrl'): raise ValueError('Missing audio source URL')
                probe_audio(str(f))
            elif not f.read_bytes().startswith(b'\xff\xd8\xff'): raise ValueError('Invalid JPEG signature')
    return raw,by_id,manifest

def run(root,content_root,dry_run=False):
    raw,enriched,manifest=validate(root)
    fingerprint=digest(packed(manifest))
    report={'records':len(raw),'series':len({q['serieId'] for q in raw}),'choices':sum(len(g['options']) for q in raw for g in q['options']),'reconstructed_prompts':sum(not q['question'].strip() for q in raw),'image_files':sum(k.startswith('images/') for k in manifest),'input_sha256':fingerprint,'local_audio':sum(bool(q.get('localAudioPath')) for q in raw)}
    if dry_run: return {'status':'dry_run',**report}
    archive=content_root/'imports'/fingerprint
    if not archive.exists():
        archive.parent.mkdir(parents=True,exist_ok=True)
        staging=archive.parent/(fingerprint+'.'+uuid.uuid4().hex+'.tmp')
        shutil.copytree(root,staging)
        actual={f.relative_to(staging).as_posix():digest(f.read_bytes()) for f in staging.rglob('*') if f.is_file()}
        if actual!=manifest: raise ValueError('Source changed during archive copy')
        staging.rename(archive)
    for name,h in manifest.items():
        if digest((archive/name).read_bytes())!=h: raise ValueError('Archive checksum mismatch')
    source=uid('source','conduire.ma'); batch=uid(source,fingerprint,VERSION)
    archive_key=f'imports/{fingerprint}'
    with connect() as c:
        # Serialize imports of this bank, including retries and changed source batches.
        c.execute('SELECT pg_advisory_lock(81732942)')
        insert(c,'ingestion.content_sources',id=source,name='Conduire.ma',base_url='https://conduire.ma',publisher_type='unverified',rights_status='unknown')
        existing=c.execute('SELECT status FROM ingestion.import_batches WHERE id=%s',(batch,)).fetchone()
        if existing and existing[0]=='complete': return {'status':'already_imported',**report}
        insert(c,'ingestion.import_batches',id=batch,source_id=source,input_sha256=fingerprint,importer_version=VERSION,enrichment_script_sha256=manifest['build_ai_dataset.py'],archive_key=archive_key,status='pending')
        c.commit()
        try:
            with c.transaction():
                series={}
                for q in raw:
                    a=enriched[q['key']]; record=uid(batch,q['key']); question=uid(source,q['key'])
                    insert(c,'ingestion.source_records',id=record,batch_id=batch,source_key=q['key'],source_series_key=str(q['serieId']),source_position=q['questionId'],source_url=f'https://conduire.ma/ar/quiz/{q["serieId"]}/jouer',raw_payload=q,raw_sha256=digest(packed(q)))
                    fields=['situation_description_darija','ai_tutor_tip_darija','common_mistake_darija','difficulty_level','keywords','legal_reference_morocco','embedding_text']
                    if not q['question'].strip(): fields.append('question_darija')
                    for field in fields:
                        insert(c,'ingestion.enrichment_candidates',id=uid(record,field),source_record_id=record,field_name=field,value=Jsonb(a[field]),producer_kind='rule_based',producer_version=manifest['build_ai_dataset.py'])
                    insert(c,'content.questions',id=question,source_id=source,source_key=q['key'],category_id='B')
                    insert(c,'ingestion.question_sources',question_id=question,source_record_id=record)
                    content_hash=digest(packed({'raw':q,'enriched':a,'media':{f:manifest[q[f]] for f in ('localImagePath','localImageAltPath','localAudioPath') if q.get(f)}}))
                    old=c.execute('SELECT id,revision_number,content_hash FROM content.question_revisions WHERE question_id=%s ORDER BY revision_number DESC LIMIT 1',(question,)).fetchone()
                    if old and old[2]==content_hash:
                        revision=old[0]
                    else:
                        number=old[1]+1 if old else 1; revision=uid(question,number,content_hash)
                        insert(c,'content.question_revisions',id=revision,question_id=question,revision_number=number,response_type='grouped' if len(q['options'])>1 else ('multiple' if len(q['correctAnswers'])>1 else 'single'),content_hash=content_hash,source_record_id=record,needs_prompt_reconstruction=not bool(q['question'].strip()))
                        insert(c,'content.question_localizations',revision_id=revision,locale='ary-MA',prompt=q['question'],explanation=q['explanation'])
                        insert(c,'content.topics',id=a['theme'],label=a['theme_label'])
                        insert(c,'content.question_topics',revision_id=revision,topic_id=a['theme'])
                        n=0
                        for pos,g in enumerate(q['options'],1):
                            group=uid(revision,'group',pos)
                            insert(c,'content.choice_groups',id=group,revision_id=revision,position=pos)
                            insert(c,'content.choice_group_localizations',group_id=group,locale='ary-MA',label=g['description'])
                            for option in g['options']:
                                n+=1; choice=uid(revision,'choice',n)
                                insert(c,'content.choices',id=choice,revision_id=revision,group_id=group,source_choice_number=n,display_position=n)
                                insert(c,'content.choice_localizations',choice_id=choice,locale='ary-MA',text=option)
                                if n in q['correctAnswers']: insert(c,'content.answer_keys',revision_id=revision,choice_id=choice)
                        for role,local_field,url_field,mime in [('original_card','localImagePath','imageUrl','image/jpeg'),('alternate','localImageAltPath','imageAltUrl','image/jpeg'),('audio','localAudioPath','audioUrl','audio/mpeg')]:
                            url=q.get(url_field)
                            if not url: continue
                            local=q.get(local_field)
                            h=manifest[local] if local else None
                            asset=uid('media',h or url)
                            old_asset=(c.execute('SELECT id FROM content.media_assets WHERE sha256=%s',(h,)).fetchone() if h else c.execute('SELECT id FROM content.media_assets WHERE source_id=%s AND original_url=%s AND sha256 IS NULL',(source,url)).fetchone())
                            if old_asset: asset=old_asset[0]
                            else: insert(c,'content.media_assets',id=asset,source_id=source,sha256=h,object_key=f'{archive_key}/{local}' if local else None,original_url=url,mime=mime,byte_size=(archive/local).stat().st_size if local else None,availability='local' if local else 'remote_only',**(probe_audio(str((archive/local).resolve())) if role=='audio' and local else {}))
                            insert(c,'content.question_media',revision_id=revision,asset_id=asset,role=role,locale='ary-MA',position=1,reveal_stage='withheld')
                    series.setdefault(q['serieId'],[]).append((q['questionId'],question,revision))
                for serie,items in series.items():
                    items.sort(); assessment=uid(source,'series',serie); pool_hash=digest(packed([[pos,str(q),str(r)] for pos,q,r in items]))
                    insert(c,'content.assessments',id=assessment,source_id=source,source_key=str(serie),kind='source_series',title=f'السلسلة {serie}')
                    last=c.execute('SELECT revision_number,pool_manifest_hash FROM content.assessment_revisions WHERE assessment_id=%s ORDER BY revision_number DESC LIMIT 1',(assessment,)).fetchone()
                    if last and last[1]==pool_hash: continue
                    number=last[0]+1 if last else 1; ar=uid(assessment,number,pool_hash)
                    insert(c,'content.assessment_revisions',id=ar,assessment_id=assessment,revision_number=number,item_count=len(items),pool_manifest_hash=pool_hash,constraints={'preserve_choice_order':True,'source_positions':True})
                    for pos,q,r in items: insert(c,'content.assessment_items',assessment_revision_id=ar,position=pos,question_id=q,question_revision_id=r)
                c.execute("UPDATE ingestion.import_batches SET status='complete',completed_at=now(),report=%s WHERE id=%s",(Jsonb(report),batch))
        except Exception as exc:
            c.rollback()
            c.execute("UPDATE ingestion.import_batches SET status='failed',completed_at=now(),report=%s WHERE id=%s",(Jsonb({'error_type':type(exc).__name__}),batch));c.commit()
            raise
    return {'status':'imported',**report}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=Path('/imports'));parser.add_argument('--content',type=Path,default=Path('/content'));parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.source,args.content,args.dry_run),ensure_ascii=False))
