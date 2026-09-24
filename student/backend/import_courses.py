"""Import a frozen courses snapshot as unreviewed content; never execute supplied SQL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import uuid
from import_dataset import connect, insert, packed, digest

NS = uuid.UUID('90949e9e-3540-4d40-aeef-4f8bf8fbf81b')
VERSION = 'courses-v1'
def uid(*values): return uuid.uuid5(NS, '|'.join(map(str,values)))

def load(root):
    datasets = {}
    for folder,key in [('lessons','lessons'),('signs','signs'),('infractions','infractions'),('license_categories','categories')]:
        document=json.loads((root/folder/(folder+'.json')).read_text(encoding='utf-8-sig'))
        datasets[folder]=document
        rows=document[key]; field={'lessons':'id','signs':'key','infractions':'id','license_categories':'code'}[folder]
        if len({x[field] for x in rows})!=len(rows): raise ValueError('Duplicate source IDs')
    signs=datasets['signs']['signs']; slugs={s['slug'] for s in signs}
    if len(slugs)!=len(signs): raise ValueError('Duplicate sign slugs')
    for sign in signs:
        relative=Path(sign['local_image_path']).relative_to('courses')
        path=(root/relative).resolve()
        if not path.is_relative_to(root.resolve()) or path.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n': raise ValueError('Invalid image')
    for row in datasets['infractions']['infractions']:
        if any(s not in slugs for s in row['related_signs']): raise ValueError('Unknown sign link')
    for lesson in datasets['lessons']['lessons']:
        if not lesson['sections']: raise ValueError('Empty lesson')
        md=(root/'lessons/lessons_md'/f"{lesson['number']:02}_{lesson['slug']}.md").read_text(encoding='utf-8')
        if any(not s['content_darija'].strip() or s['content_darija'] not in md for s in lesson['sections']): raise ValueError('Markdown mismatch')
    return datasets

def run(root, content, dry_run):
    data=load(root)
    manifest={p.relative_to(root).as_posix():digest(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}
    package_hash=digest(packed(manifest)); source=uid('source'); batch=uid('batch',package_hash)
    report={'lessons':len(data['lessons']['lessons']),'sections':sum(len(l['sections']) for l in data['lessons']['lessons']),
        'signs':len(data['signs']['signs']),'infractions_staged':len(data['infractions']['infractions']),
        'categories_staged':len(data['license_categories']['categories']),'status':'draft','package_sha256':package_hash}
    if dry_run: print(json.dumps(report)); return
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(VERSION,))
        insert(c,'ingestion.content_sources',id=source,name='PerminIA courses snapshot',base_url='local:permis-courses',publisher_type='unverified',rights_status='unknown')
        if c.execute("SELECT 1 FROM ingestion.import_batches WHERE id=%s AND status='complete'",(batch,)).fetchone():
            print(json.dumps(dict(report,result='unchanged'))); return
        insert(c,'ingestion.import_batches',id=batch,source_id=source,input_sha256=package_hash,importer_version=VERSION,
            enrichment_script_sha256=digest(Path(__file__).read_bytes()),archive_key=str(root),status='pending',report=report)
        # Keep all source metadata and unreviewed legal records out of the student API and AI corpus.
        for folder,document in data.items():
            insert(c,'ingestion.source_records',id=uid(batch,folder,'raw'),batch_id=batch,source_key=folder+':raw',source_series_key=folder,
                source_position=1,source_url='local:'+folder,raw_payload=document,raw_sha256=digest(packed(document)))
        for lesson in data['lessons']['lessons']:
            key=lesson['id']; sha=digest(packed(lesson)); record=uid(batch,key); lid=uid('lesson',key); rev=uid('lesson',key,sha)
            insert(c,'ingestion.source_records',id=record,batch_id=batch,source_key=key,source_series_key='lessons',source_position=lesson['number'],source_url='local:'+key,raw_payload=lesson,raw_sha256=sha)
            insert(c,'content.lessons',id=lid,source_id=source,source_key=key,slug=lesson['slug'],position=lesson['number'])
            insert(c,'content.lesson_revisions',id=rev,lesson_id=lid,source_record_id=record,content_hash=sha,title_ar=lesson['title_ar'],summary_darija=lesson['summary_darija'],common_mistakes_darija=lesson['common_mistakes_darija'],coach_tip=lesson['ai_coach_tip'])
            for pos,section in enumerate(lesson['sections'],1):
                insert(c,'content.lesson_sections',revision_id=rev,position=pos,title_ar=section['subtitle_ar'],body_darija=section['content_darija'])
        for pos,sign in enumerate(data['signs']['signs'],1):
            key=sign['key']; sha=digest(packed(sign)); record=uid(batch,'sign',key)
            path=root/Path(sign['local_image_path']).relative_to('courses'); image_hash=digest(path.read_bytes()); object_key=f'courses/{image_hash}.png'
            target=content/object_key; target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists(): shutil.copyfile(path,target)
            if digest(target.read_bytes())!=image_hash: raise ValueError('Stored image hash mismatch')
            existing=c.execute('SELECT id FROM content.media_assets WHERE sha256=%s',(image_hash,)).fetchone()
            asset=existing[0] if existing else uid('asset',image_hash)
            if not existing: insert(c,'content.media_assets',id=asset,source_id=source,sha256=image_hash,object_key=object_key,original_url=sign['image_url'],mime='image/png',byte_size=path.stat().st_size,availability='local')
            insert(c,'ingestion.source_records',id=record,batch_id=batch,source_key='sign:'+key,source_series_key='signs',source_position=pos,source_url=sign['image_url'],raw_payload=sign,raw_sha256=sha)
            insert(c,'content.road_sign_revisions',id=uid('sign',key,sha),source_record_id=record,source_key=key,slug=sign['slug'],section_name=sign['section_title_ar'],title_ar=sign['title_ar'],meaning_darija=sign['meaning_darija'],asset_id=asset,content_hash=sha)
        c.execute("UPDATE ingestion.import_batches SET status='complete',completed_at=now() WHERE id=%s",(batch,))
    print(json.dumps(dict(report,result='imported')))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--content',type=Path,default=Path('/content'));p.add_argument('--dry-run',action='store_true');a=p.parse_args();run(a.root,a.content,a.dry_run)
