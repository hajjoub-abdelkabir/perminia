"""Reading suggestions derived exclusively from the student's saved activity."""
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Depends,Response
from sqlalchemy import text
from app.db import engine
from app.lessons import scope
from app.auth import require_school_student
from app.student import preview_enabled

router=APIRouter(prefix='/api/v1/student/journey',dependencies=[Depends(preview_enabled)])

def arrange(sections,minutes):
    target=max(1,min(6,minutes//5))
    done=sum(bool(s['completed'] and s['done_today']) for s in sections)
    remaining=[s for s in sections if not s['completed']]
    tasks=remaining[:max(0,target-done)]
    saved=[s for s in sections if s['updated_at']]
    resume=max(saved,key=lambda s:s['updated_at']) if saved else (remaining[0] if remaining else None)
    return {'target':target,'completed_today':done,'target_met':done>=target,'tasks':tasks,
      'resume':resume,'all_read':bool(sections) and not remaining,
      'bookmarks':[s for s in sections if s['bookmarked']][:3],
      'estimated_minutes_per_section':5,'policy':'reading-plan-v1'}

@router.get('/daily-plan')
def daily_plan(response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    day=datetime.now(ZoneInfo('Africa/Casablanca')).date()
    with engine.begin() as c:
        scope(c,user)
        minutes=c.execute(text('SELECT daily_minutes FROM learning.journey_profiles')).scalar_one_or_none() or 20
        sections=[dict(r) for r in c.execute(text('''SELECT l.slug,l.title_ar AS lesson_title,l.revision_id,
          s.position,s.title_ar AS title,coalesce(p.completed,false) AS completed,
          coalesce(p.bookmarked,false) AS bookmarked,p.updated_at,
          EXISTS(SELECT 1 FROM learning.reading_activity a WHERE a.revision_id=l.revision_id
            AND a.section_position=s.position AND a.day=:day AND a.origin='completion') AS done_today
          FROM content.preview_lessons l JOIN content.preview_lesson_sections s ON s.revision_id=l.revision_id
          LEFT JOIN learning.lesson_section_progress p ON p.revision_id=l.revision_id AND p.section_position=s.position
          ORDER BY l.position,s.position,l.id'''),{'day':day}).mappings()]
    return {'day':day,'daily_minutes':minutes,**arrange(sections,minutes)}
