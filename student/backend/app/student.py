"""Local, non-grading student preview. Never expose arbitrary volume paths."""
import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine


def preview_enabled():
    if os.environ.get('STUDENT_PREVIEW_ENABLED') != 'true':
        raise HTTPException(404, 'Preview disabled')


router = APIRouter(prefix='/api/v1/student/preview', dependencies=[Depends(preview_enabled)])


def rows(sql, **params):
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(sql), params).mappings()]
    except SQLAlchemyError:
        raise HTTPException(503, 'Content temporarily unavailable') from None


@router.get('/series')
def series():
    items = rows('SELECT id,title,source_key,revision_id,item_count FROM content.preview_series ORDER BY source_key')
    items.sort(key=lambda item: int(''.join(filter(str.isdigit, item['source_key'])) or 0))
    return {'mode': 'local_preview', 'items': items}


@router.get('/series/{series_id}')
def series_questions(series_id: UUID):
    items = rows('SELECT id,title,item_count FROM content.preview_series WHERE id=:id', id=series_id)
    if not items:
        raise HTTPException(404, 'Series not found')
    questions = rows('SELECT position,revision_id,response_type,prompt,choices,groups FROM content.preview_questions WHERE series_id=:id ORDER BY position', id=series_id)
    media = rows('SELECT m.revision_id,m.asset_id,m.role,m.duration_seconds FROM content.preview_media m JOIN content.preview_questions q ON q.revision_id=m.revision_id WHERE q.series_id=:id ORDER BY m.position', id=series_id)
    for question in questions:
        question['media'] = [
            {'role': m['role'], 'url': f"/api/v1/student/preview/media/{m['asset_id']}", 'duration_seconds': m['duration_seconds']}
            for m in media if m['revision_id'] == question['revision_id']
        ]
    return {'mode': 'local_preview', 'series': items[0], 'questions': questions}


@router.get('/media/{asset_id}')
def media_file(asset_id: UUID):
    media = rows('SELECT object_key,mime FROM content.preview_media WHERE asset_id=:id LIMIT 1', id=asset_id)
    if not media:
        raise HTTPException(404, 'Media not found')
    root = Path('/content').resolve()
    path = (root / media[0]['object_key']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, 'Media unavailable')
    return FileResponse(path, media_type=media[0]['mime'], headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, max-age=3600'})
