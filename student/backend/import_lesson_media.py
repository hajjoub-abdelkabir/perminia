"""Import immutable source assets. Source 'approved' never grants publication."""
import hashlib
import json
import mimetypes
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET
from sqlalchemy import text
from app.db import engine

ROOT=Path('/lesson-import').resolve()
STORE=Path('/content')

def source_file(relative):
    path=(ROOT/relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('Missing or escaping source file')
    return path

def validate_svg(path):
    for node in ET.parse(path).iter():
        if node.tag.split('}')[-1] in ('script','foreignObject'):
            raise ValueError('Active SVG')
        for key,value in node.attrib.items():
            if key.lower().startswith('on') or (key.split('}')[-1]=='href' and not value.startswith('#')):
                raise ValueError('External or active SVG')

def main(manifest=None,mapping=None,source_name='lesson-media-2026-09-13',preview_videos=()):
    manifest=manifest or json.loads(source_file('manifests/lesson_media_manifest.json').read_text(encoding='utf-8'))
    mapping=mapping or json.loads(source_file('manifests/lesson_media_mapping.json').read_text(encoding='utf-8'))
    references={ref['asset_id']:(lesson['slug'],int(section['section_id'].split('_')[-1]),ref['display_order'])
        for lesson in mapping['lessons'] for section in lesson['sections'] for ref in section['media_assets']}
    prepared=[]
    for asset in manifest['assets']:
        path=source_file(asset['local_path']); digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=asset['sha256']: raise ValueError('Asset digest mismatch: '+asset['asset_id'])
        if path.suffix=='.svg': validate_svg(path)
        if asset['asset_id'] not in references: raise ValueError('Unmapped asset')
        slug,position,order=references[asset['asset_id']]
        # Regulatory/first-aid material, external rights and motion scenarios need separate review.
        hold=asset['origin']!='generated' or (asset['media_type']=='video' and asset['asset_id'] not in preview_videos) or asset['lesson_source_id'] in ('lesson_04','lesson_06','lesson_07','lesson_09')
        prepared.append((asset,path,digest,slug,position,order,'hold' if hold else 'preview'))
    with engine.begin() as c:
        source=c.execute(text("INSERT INTO ingestion.content_sources(name,base_url) VALUES(:name,'local:lesson_media') ON CONFLICT(name) DO UPDATE SET name=excluded.name RETURNING id"),{'name':source_name}).scalar_one()
        count={'preview':0,'hold':0}
        for asset,path,digest,slug,position,order,state in prepared:
            section=c.execute(text('SELECT s.revision_id,s.body_darija FROM content.preview_lesson_sections s JOIN content.preview_lessons l ON l.revision_id=s.revision_id WHERE l.slug=:slug AND s.position=:position'),{'slug':slug,'position':position}).mappings().one()
            if hashlib.sha256(section['body_darija'].strip().encode()).hexdigest()!=asset['source_text_hash']:
                raise ValueError('Lesson text differs: '+slug)
            key='lesson-media/'+digest+path.suffix.lower(); target=STORE/key
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists(): shutil.copyfile(path,target)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=digest: raise ValueError('Stored asset mismatch')
            aid=c.execute(text('''INSERT INTO content.media_assets(source_id,sha256,object_key,original_url,mime,byte_size,availability)
              VALUES(:source,:sha,:key,:url,:mime,:size,'local') ON CONFLICT(sha256) DO NOTHING RETURNING id'''),
              {'source':source,'sha':digest,'key':key,'url':'local:'+asset['local_path'],'mime':mimetypes.guess_type(path)[0] or 'application/octet-stream','size':path.stat().st_size}).scalar_one_or_none()
            if aid is None: aid=c.execute(text('SELECT id FROM content.media_assets WHERE sha256=:sha'),{'sha':digest}).scalar_one()
            metadata={**asset,'source_exact_source_excerpt':asset['exact_source_excerpt'],'exact_source_excerpt':section['body_darija'],'import_note':'Source approval unverified; preview is not publication.'}
            for role in ('poster','captions'):
                relative=asset.get(role+'_path')
                if relative:
                    aux=source_file(relative)
                    expected='.png' if role=='poster' else '.vtt'
                    if aux.suffix.lower()!=expected: raise ValueError('Unexpected companion type')
                    if role=='captions' and not aux.read_text(encoding='utf-8-sig').startswith('WEBVTT'): raise ValueError('Invalid captions')
                    sha=hashlib.sha256(aux.read_bytes()).hexdigest();auxkey='lesson-media/'+sha+expected
                    destination=STORE/auxkey
                    if not destination.exists(): shutil.copyfile(aux,destination)
                    if hashlib.sha256(destination.read_bytes()).hexdigest()!=sha: raise ValueError('Companion hash mismatch')
                    metadata[role+'_object_key']=auxkey
            c.execute(text('''INSERT INTO content.lesson_media(revision_id,section_position,asset_id,source_key,concept_key,source_text_hash,display_order,review_state,metadata)
              VALUES(:revision,:position,:asset,:source,:concept,:hash,:ordering,:state,CAST(:metadata AS jsonb)) ON CONFLICT DO NOTHING'''),
              {'revision':section['revision_id'],'position':position,'asset':aid,'source':asset['asset_id'],'concept':asset['concept_id'],'hash':asset['source_text_hash'],'ordering':order,'state':state,'metadata':json.dumps(metadata,ensure_ascii=False)})
            if state=='preview' and asset.get('supersedes_asset_id'):
                c.execute(text("UPDATE content.lesson_media SET review_state='hold' WHERE revision_id=:rev AND section_position=:position AND source_key=:old AND asset_id<>:new"),{'rev':section['revision_id'],'position':position,'old':asset['supersedes_asset_id'],'new':aid})
            if state=='preview' and source_name=='lesson-media-v2-2026-09-14':
                # Some v2 supersedes identifiers are incorrect. Match the already verified
                # section and media kind within v1's source, never another package.
                c.execute(text("""UPDATE content.lesson_media SET review_state='hold'
                    WHERE revision_id=:rev AND section_position=:position AND asset_id<>:new
                    AND metadata->>'media_type'=:kind AND asset_id IN (
                    SELECT a.id FROM content.media_assets a JOIN ingestion.content_sources s ON s.id=a.source_id
                    WHERE s.name='lesson-media-2026-09-13')"""),
                    {'rev':section['revision_id'],'position':position,'new':aid,'kind':asset['media_type']})
            count[state]+=1
    print(json.dumps(count))

if __name__=='__main__': main()
