"""Self-reported review needs and effort, independent of grading/mastery."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Response,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import text
from app.db import engine
from app.lessons import scope
from app.auth import require_school_student,protect_mutation
from app.student import preview_enabled

router=APIRouter(prefix='/api/v1/student/journey/notebook',dependencies=[Depends(preview_enabled)])
def today():return datetime.now(ZoneInfo('Africa/Casablanca')).date()
def query(c,s,**p):return c.execute(text(s),p)

class Save(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['lesson','question']
    revision_id:UUID
    section_position:int|None=Field(default=None,ge=1,le=100)
    reason:Literal['unclear','hesitated','ask']
    note:str=Field(default='',max_length=600)
    @model_validator(mode='after')
    def target(self):
        if (self.kind=='lesson')!=(self.section_position is not None):raise ValueError('Invalid target')
        return self

class Change(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)
    action:Literal['review','snooze','close','reopen']
    days:Literal[1,3,7]=1

@router.post('',dependencies=[Depends(protect_mutation)])
def save(body:Save,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user)
        if body.kind=='lesson':
            valid=query(c,'SELECT 1 FROM content.preview_lesson_sections WHERE revision_id=:r AND position=:p',r=body.revision_id,p=body.section_position).first()
        else:valid=query(c,'SELECT 1 FROM content.preview_questions WHERE revision_id=:r LIMIT 1',r=body.revision_id).first()
        if not valid:raise HTTPException(404,'هاد المحتوى ما بقاش متاح.')
        # Member-scoped serialization makes duplicate clicks/retries one entry.
        query(c,"SELECT pg_advisory_xact_lock(hashtextextended(:key,0))",key='notebook:'+str(user['membership_id']))
        existing=query(c,'''SELECT * FROM learning.review_notebook WHERE kind=:kind AND
          (question_revision_id=:r OR (lesson_revision_id=:r AND section_position=:p)) FOR UPDATE''',kind=body.kind,r=body.revision_id,p=body.section_position).mappings().first()
        if existing:
            # Marking again updates notes but does not reset a postponed date or reopen a closed entry.
            if existing['reason']!=body.reason or existing['note']!=body.note:
                query(c,'UPDATE learning.review_notebook SET reason=:reason,note=:note,version=version+1,updated_at=now() WHERE id=:id',reason=body.reason,note=body.note,id=existing['id'])
            return {'saved':True,'id':existing['id']}
        ident=query(c,'''INSERT INTO learning.review_notebook(tenant_id,membership_id,kind,lesson_revision_id,section_position,question_revision_id,reason,note,due_on)
          VALUES(:t,:m,:kind,:l,:p,:q,:reason,:note,:day) RETURNING id''',t=user['tenant_id'],m=user['membership_id'],kind=body.kind,l=body.revision_id if body.kind=='lesson' else None,p=body.section_position,q=body.revision_id if body.kind=='question' else None,reason=body.reason,note=body.note,day=today()).scalar_one()
        return {'saved':True,'id':ident}

@router.patch('/{entry_id}',dependencies=[Depends(protect_mutation)])
def change(entry_id:UUID,body:Change,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user);row=query(c,'SELECT * FROM learning.review_notebook WHERE id=:id FOR UPDATE',id=entry_id).mappings().first()
        if not row:raise HTTPException(404,'العنصر ما تلقاش.')
        if row['version']!=body.expected_version:raise HTTPException(409,'تبدلات الحالة. حدّث الدفتر وعاود جرّب.')
        if row['state']=='done' and body.action!='reopen':raise HTTPException(409,'المراجعة مسالية. افتحها من جديد أولاً.')
        day=today();due=day+timedelta(days=body.days) if body.action in ('review','snooze') else day
        query(c,"UPDATE learning.review_notebook SET state=:state,due_on=:due,version=version+1,updated_at=now() WHERE id=:id",state='done' if body.action=='close' else 'open',due=due,id=entry_id)
        if body.action in ('review','close'):
            query(c,'INSERT INTO learning.notebook_activity VALUES(:t,:m,:id,:day) ON CONFLICT DO NOTHING',t=user['tenant_id'],m=user['membership_id'],id=entry_id,day=day)
    return {'saved':True}

@router.get('')
def listing(response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store';day=today()
    with engine.begin() as c:
        scope(c,user)
        items=[dict(r) for r in query(c,'''SELECT n.*,l.slug,l.title_ar AS lesson_title,s.title_ar AS section_title,
          q.prompt,q.choices,q.series_id,
          CASE WHEN n.kind='lesson' THEN l.id IS NOT NULL ELSE q.revision_id IS NOT NULL END AS available
          FROM learning.review_notebook n
          LEFT JOIN content.preview_lessons l ON l.revision_id=n.lesson_revision_id
          LEFT JOIN content.preview_lesson_sections s ON s.revision_id=n.lesson_revision_id AND s.position=n.section_position
          LEFT JOIN LATERAL(SELECT revision_id,prompt,choices,series_id FROM content.preview_questions WHERE revision_id=n.question_revision_id LIMIT 1) q ON true
          ORDER BY (n.state='done'),n.due_on,n.created_at''').mappings()]
        for item in items:
            item['due']=item['state']=='open' and item['due_on']<=day
            item['image_url']=None
            if item['kind']=='question' and item['available']:
                asset=query(c,"SELECT asset_id FROM content.preview_media WHERE revision_id=:r AND role='original_card' LIMIT 1",r=item['question_revision_id']).scalar_one_or_none()
                if asset:item['image_url']='/api/v1/student/preview/media/'+str(asset)
        # Independent seven-day summary, excludes demo performance and backfilled activity.
        start=day-timedelta(days=6)
        readings=query(c,"SELECT day,count(*) AS n FROM learning.reading_activity WHERE day BETWEEN :start AND :day AND origin='completion' GROUP BY day",start=start,day=day).mappings().all()
        reviews=query(c,'SELECT day,count(*) AS n FROM learning.notebook_activity WHERE day BETWEEN :start AND :day GROUP BY day',start=start,day=day).mappings().all()
        runs=query(c,"SELECT (closed_at AT TIME ZONE 'Africa/Casablanca')::date AS day,count(*) AS n FROM learning.training_runs WHERE state='completed' AND EXISTS(SELECT 1 FROM learning.training_items i JOIN learning.training_answers a ON a.item_id=i.id WHERE i.run_id=learning.training_runs.id AND a.status='answered') AND (closed_at AT TIME ZONE 'Africa/Casablanca')::date BETWEEN :start AND :day GROUP BY 1",start=start,day=day).mappings().all()
        active={r['day'] for r in [*readings,*reviews,*runs]}
        timeline=[{'day':start+timedelta(days=i),'active':start+timedelta(days=i) in active} for i in range(7)]
    return {'items':items,'day':day,'due_count':sum(i['due'] for i in items),
      'week':{'days':timeline,'active_days':len(active),'sections':sum(r['n'] for r in readings),'reviews':sum(r['n'] for r in reviews),'runs':sum(r['n'] for r in runs),
      'badges':(['بداية المراجعة'] if active else [])+(['3 أيام نشاط'] if len(active)>=3 else [])+(['أسبوع نشيط'] if len(active)==7 else [])}}
