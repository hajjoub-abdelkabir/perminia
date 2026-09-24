"""Adapt v2 using the previously verified v1 section hashes, not its null claims."""
import json
from pathlib import Path
import import_lesson_media as importer

def main():
    previous=Path('/previous-import/manifests')
    old=json.loads((previous/'lesson_media_manifest.json').read_text(encoding='utf-8'))
    oldmap=json.loads((previous/'lesson_media_mapping.json').read_text(encoding='utf-8'))
    hashes={(a['lesson_source_id'],a['section_source_id']):a['source_text_hash'] for a in old['assets']}
    slugs={l['lesson_id']:l['slug'] for l in oldmap['lessons']}
    raw=json.loads(importer.source_file('manifests/lesson_media_manifest.json').read_text(encoding='utf-8'))
    assets=[];mapped={}
    for original in raw['assets']:
        a=dict(original);key=(a['lesson_id'],a['section_id'])
        a['source_declared_text_hash']=a.get('source_text_hash')
        a['source_text_hash']=hashes[key]
        a['hash_binding_method']='v1 section reference; verified against database on import'
        a['source_original_metadata']=original
        a['lesson_source_id'],a['section_source_id']=key
        a['media_type']='video' if original['media_type']=='video_mp4' else 'image'
        a['origin']='generated' if original['origin'].startswith('generated') else 'downloaded'
        assets.append(a)
        refs=mapped.setdefault(key,[])
        refs.append({'asset_id':a['asset_id'],'display_order':len(refs)+1})
    mapping={'lessons':[{'slug':slug,'sections':[{'section_id':section,'media_assets':refs} for (lid,section),refs in mapped.items() if lid==lesson]} for lesson,slug in slugs.items()]}
    importer.main({'assets':assets},mapping,'lesson-media-v2-2026-09-14',preview_videos=('vid_b_overtaking_phases',))

if __name__=='__main__': main()
