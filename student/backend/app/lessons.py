"""Explicit local preview; no reviewed curriculum or AI legal reference implied."""
from uuid import UUID
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from app.db import engine
from app.student import preview_enabled, rows
from app.auth import require_school_student, protect_mutation

router=APIRouter(prefix='/api/v1/student/preview',dependencies=[Depends(preview_enabled)])

def scope(c,user):
    c.execute(text("SELECT set_config('app.tenant_id',:tenant,true),set_config('app.membership_id',:member,true)"),{'tenant':str(user['tenant_id']),'member':str(user['membership_id'])})

@router.get('/lessons')
def library():
    return {'mode':'local_preview','items':rows('SELECT id,slug,position,revision_id,title_ar,summary_darija,status,section_count FROM content.preview_lessons ORDER BY position')}

@router.get('/lessons/{slug}')
def lesson(slug:str):
    found=rows('SELECT * FROM content.preview_lessons WHERE slug=:slug',slug=slug)
    if not found: raise HTTPException(404,'الدرس ما تلقاش.')
    sections=rows('SELECT * FROM content.preview_lesson_sections WHERE revision_id=:rev ORDER BY position',rev=found[0]['revision_id'])
    media=rows("SELECT section_position,asset_id,metadata->>'title_ar' AS title,metadata->>'alt_text_darija' AS alt,metadata->>'media_type' AS media_type,metadata->>'transcript_darija' AS video_summary,metadata->>'poster_object_key' IS NOT NULL AS has_poster,metadata->>'captions_object_key' IS NOT NULL AS has_captions FROM content.preview_lesson_media WHERE revision_id=:rev ORDER BY display_order,source_key",rev=found[0]['revision_id'])
    for section in sections:
        section['media']=[{**m,'url':'/api/v1/student/preview/lesson-media/'+str(m['asset_id'])} for m in media if m['section_position']==section['position']]
    return {'lesson':found[0],'sections':sections}

@router.get('/lesson-media/{asset_id}/{role}')
def lesson_media_companion(asset_id:UUID,role:str):
    if role not in ('poster','captions'): raise HTTPException(404)
    found=rows("SELECT metadata->>:key AS object_key FROM content.preview_lesson_media WHERE asset_id=:id LIMIT 1",key=role+'_object_key',id=asset_id)
    if not found or not found[0]['object_key']: raise HTTPException(404)
    root=Path('/content').resolve();path=(root/found[0]['object_key']).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise HTTPException(404)
    return FileResponse(path,media_type='image/png' if role=='poster' else 'text/vtt',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=300'})

@router.get('/lesson-media/{asset_id}')
def lesson_media(asset_id:UUID):
    found=rows('SELECT object_key,mime FROM content.preview_lesson_media WHERE asset_id=:id LIMIT 1',id=asset_id)
    if not found: raise HTTPException(404)
    root=Path('/content').resolve();path=(root/found[0]['object_key']).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise HTTPException(404)
    return FileResponse(path,media_type=found[0]['mime'],headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=300','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; sandbox"})

@router.get('/lesson-progress')
def progress(response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user)
        return {'items':[dict(r) for r in c.execute(text('SELECT revision_id,section_position,completed,bookmarked,updated_at FROM learning.lesson_section_progress ORDER BY updated_at')).mappings()]}

class Progress(BaseModel):
    model_config=ConfigDict(extra='forbid')
    section_position:int=Field(ge=1,le=100)
    completed:bool|None=None
    bookmarked:bool|None=None

@router.put('/lesson-progress/{revision_id}',dependencies=[Depends(protect_mutation)])
def save(revision_id:UUID,body:Progress,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user)
        if not c.execute(text('SELECT 1 FROM content.preview_lesson_sections WHERE revision_id=:rev AND position=:pos'),{'rev':revision_id,'pos':body.section_position}).first(): raise HTTPException(404,'الفقرة ما تلقاتش.')
        c.execute(text('''INSERT INTO learning.lesson_section_progress(tenant_id,membership_id,revision_id,section_position,completed,bookmarked)
            VALUES(:tenant,:member,:rev,:pos,coalesce(:done,false),coalesce(:mark,false))
            ON CONFLICT(tenant_id,membership_id,revision_id,section_position) DO UPDATE
            SET completed=coalesce(:done,lesson_section_progress.completed),bookmarked=coalesce(:mark,lesson_section_progress.bookmarked),updated_at=now()'''),
            {'tenant':user['tenant_id'],'member':user['membership_id'],'rev':revision_id,'pos':body.section_position,'done':body.completed,'mark':body.bookmarked})
    return {'saved':True}

@router.get('/signs')
def signs():
    return {'items':rows('SELECT id,source_key,section_name,title_ar,meaning_darija,asset_id FROM content.preview_signs ORDER BY source_key')}

@router.get('/sign-media/{asset_id}')
def sign_media(asset_id:UUID):
    found=rows('SELECT object_key,mime FROM content.preview_signs WHERE asset_id=:id LIMIT 1',id=asset_id)
    if not found: raise HTTPException(404)
    root=Path('/content').resolve();path=(root/found[0]['object_key']).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise HTTPException(404)
    return FileResponse(path,media_type=found[0]['mime'],headers={'X-Content-Type-Options':'nosniff'})
