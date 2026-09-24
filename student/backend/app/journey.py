"""Private student analytics. Synthetic scores and real participation stay separate."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from uuid import UUID
import json
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from app.auth import require_school_student, protect_mutation
from app.db import engine
from app.lessons import scope

router = APIRouter(prefix='/api/v1/student/journey')
TZ = ZoneInfo('Africa/Casablanca')

def today():
    return datetime.now(TZ).date()

def aggregate(records):
    total = sum(r['total'] for r in records)
    return round(100 * sum(r['correct'] for r in records) / total) if total else None

def snapshot(user):
    with engine.begin() as c:
        scope(c,user)
        profile = c.execute(text('SELECT * FROM learning.journey_profiles')).mappings().first()
        profile = dict(profile) if profile else dict(enrolled_on=None,exam_on=None,daily_minutes=20,fixture_version=None,persona=None)
        records = [dict(r) for r in c.execute(text('SELECT d.*,l.title_ar,l.slug FROM learning.demo_performance d JOIN content.preview_lessons l ON l.id=d.lesson_id ORDER BY occurred_at')).mappings()]
        sessions = [dict(r) for r in c.execute(text("""SELECT * FROM (
          SELECT id,recorded_at,jsonb_array_length(outcomes) AS total,(SELECT count(*) FROM jsonb_array_elements(outcomes) o WHERE o->>'status'='answered') AS answered FROM learning.preview_sessions
          UNION ALL SELECT r.id,r.closed_at AS recorded_at,count(i.id) AS total,count(a.item_id) FILTER(WHERE a.status='answered') AS answered
          FROM learning.training_runs r JOIN learning.training_items i ON i.run_id=r.id LEFT JOIN learning.training_answers a ON a.item_id=i.id
          WHERE r.state='completed' GROUP BY r.id,r.closed_at) s ORDER BY recorded_at DESC LIMIT 100""")).mappings()]
        lesson_rows = [dict(r) for r in c.execute(text('''SELECT l.id,l.slug,l.title_ar,l.section_count,count(p.section_position) FILTER(WHERE p.completed) AS completed
          FROM content.preview_lessons l LEFT JOIN learning.lesson_section_progress p ON p.revision_id=l.revision_id
          GROUP BY l.id,l.slug,l.title_ar,l.section_count,l.position ORDER BY l.position''')).mappings()]
        session_count=c.execute(text("SELECT (SELECT count(*) FROM learning.preview_sessions)+(SELECT count(*) FROM learning.training_runs WHERE state='completed')")).scalar_one()
        activity = [r[0] for r in c.execute(text("SELECT day FROM learning.reading_activity UNION SELECT (recorded_at AT TIME ZONE 'Africa/Casablanca')::date FROM learning.preview_sessions UNION SELECT (received_at AT TIME ZONE 'Africa/Casablanca')::date FROM learning.training_answers WHERE status='answered'"))]
    now = today()
    recent = [r for r in records if r['occurred_at'].astimezone(TZ).date() >= now-timedelta(days=13)]
    previous = [r for r in records if now-timedelta(days=27) <= r['occurred_at'].astimezone(TZ).date() < now-timedelta(days=13)]
    score, baseline = aggregate(recent), aggregate(previous)
    topics = []
    for lesson in lesson_rows:
        subset = [r for r in recent if r['lesson_id']==lesson['id']]
        topics.append({**lesson,'score':aggregate(subset),'sample':sum(r['total'] for r in subset)})
    weakest = sorted([t for t in topics if t['score'] is not None],key=lambda t:t['score'])
    next_lesson = next((l for l in lesson_rows if l['completed']<l['section_count']), None)
    focus = weakest[0] if weakest else next_lesson
    days = defaultdict(lambda: {'minutes':0,'samples':[],'real_events':0})
    for r in records:
        day=r['occurred_at'].astimezone(TZ).date(); days[day]['minutes']+=r['minutes'];days[day]['samples'].append(r)
    for r in sessions:
        days[r['recorded_at'].astimezone(TZ).date()]['real_events']+=1
    for day in activity:
        days[day]['real_events']+=1
    active_dates=set(days)
    cursor=now if now in active_dates else now-timedelta(days=1)
    streak=0
    while cursor in active_dates:
        streak+=1;cursor-=timedelta(days=1)
    timeline=[{'date':now-timedelta(days=i),'minutes':days[now-timedelta(days=i)]['minutes'],
        'score':aggregate(days[now-timedelta(days=i)]['samples']),
        'active':now-timedelta(days=i) in active_dates} for i in reversed(range(28))]
    training_minutes=20 if profile['daily_minutes']>=25 else profile['daily_minutes']-profile['daily_minutes']//2
    full_session=profile['daily_minutes']>=25
    plan=[{'title':'فهم قبل الحفظ','body':('رجع لمحور '+focus['title_ar']+' وخذ فكرة وحدة بشوية.') if focus else 'بدا بأول درس وخذ فكرة وحدة بشوية.','page':'lessons','minutes':profile['daily_minutes']-training_minutes},
          {'title':'جولة تدريب' if full_session else 'تثبيت الفكرة','body':'جرّب سلسلة، سمع السؤال وأكد الاختيار ديالك قبل ما يسالي الوقت.' if full_session else 'رجع للمشهد ديال المحور وحاول تشرح الفكرة بكلامك.','page':'series' if full_session else 'lessons','minutes':training_minutes}]
    return {'profile':{k:profile[k] for k in ('enrolled_on','exam_on','daily_minutes','persona')},
        'is_demo':bool(profile['fixture_version']), 'as_of':now, 'days_left':(profile['exam_on']-now).days if profile['exam_on'] else None,
        'score':score,'score_change':score-baseline if score is not None and baseline is not None else None,
        'sample_size':sum(r['total'] for r in recent),'demo_sessions':len(records),'real_sessions':sessions,'real_session_count':session_count,
        'streak':streak,'completed_sections':sum(l['completed'] for l in lesson_rows),'total_sections':sum(l['section_count'] for l in lesson_rows),
        'topics':topics,'timeline':timeline,'plan':plan,'focus':focus,
        'score_basis':'synthetic_fixture_only','readiness':'غير محسومة — مازال خاص تصحيح معتمد وتقييم الأستاذ',
        'history':[{'date':r['occurred_at'],'title':r['title_ar'],'score':aggregate([r]),'total':r['total'],'demo':True} for r in reversed(records[-12:])]}

@router.get('')
def dashboard(response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    return snapshot(user)

class Goal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    exam_on:date|None=None
    daily_minutes:int=Field(ge=5,le=120)

@router.put('/goal',dependencies=[Depends(protect_mutation)])
def goal(body:Goal,response:Response,user=Depends(require_school_student)):
    if body.exam_on and not today()<=body.exam_on<=today()+timedelta(days=730):
        raise HTTPException(422,'اختار موعد من اليوم حتى لعامين، أو خليه فارغ.')
    with engine.begin() as c:
        scope(c,user)
        c.execute(text('''INSERT INTO learning.journey_profiles(tenant_id,membership_id,exam_on,daily_minutes)
         VALUES(:t,:m,:exam,:minutes) ON CONFLICT(tenant_id,membership_id) DO UPDATE SET exam_on=excluded.exam_on,daily_minutes=excluded.daily_minutes'''),
         dict(t=user['tenant_id'],m=user['membership_id'],exam=body.exam_on,minutes=body.daily_minutes))
    response.headers['Cache-Control']='no-store'
    return {'saved':True}

class Outcome(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision_id:UUID
    status:Literal['answered','expired','skipped']
    choices:list[UUID]=Field(default_factory=list,max_length=20)

class Participation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    series_id:UUID
    outcomes:list[Outcome]=Field(min_length=1,max_length=100)

@router.put('/sessions/{session_id}',dependencies=[Depends(protect_mutation)])
def participation(session_id:UUID,body:Participation,response:Response,user=Depends(require_school_student)):
    payload=json.dumps([o.model_dump(mode='json') for o in body.outcomes],sort_keys=True)
    with engine.begin() as c:
        scope(c,user)
        allowed={str(r['revision_id']):{str(v['id']) for v in (r['choices'] or [])} for r in c.execute(text('SELECT revision_id,choices FROM content.preview_questions WHERE series_id=:id'),{'id':body.series_id}).mappings()}
        ids=[str(o.revision_id) for o in body.outcomes]
        if not allowed or len(set(ids))!=len(ids) or set(ids)!=set(allowed): raise HTTPException(422,'خاص الجولة تكون كاملة والأسئلة ديال نفس السلسلة.')
        for o in body.outcomes:
            if not set(map(str,o.choices))<=allowed[str(o.revision_id)] or len(o.choices)!=len(set(o.choices)) or (o.status=='answered')!=bool(o.choices):
                raise HTTPException(422,'الاختيارات ما مطابْقاش لحالة الجواب.')
        saved=c.execute(text('''INSERT INTO learning.preview_sessions(id,tenant_id,membership_id,series_id,outcomes)
          VALUES(:id,:t,:m,:series,CAST(:payload AS jsonb)) ON CONFLICT DO NOTHING RETURNING id'''),dict(id=session_id,t=user['tenant_id'],m=user['membership_id'],series=body.series_id,payload=payload)).first()
        if not saved:
            old=c.execute(text('SELECT series_id,outcomes FROM learning.preview_sessions WHERE id=:id'),{'id':session_id}).mappings().one()
            if old['series_id']!=body.series_id or old['outcomes']!=json.loads(payload): raise HTTPException(409,'الجولة مسجلة من قبل بمعطيات أخرى.')
    response.headers['Cache-Control']='no-store'
    return {'saved':True,'graded':False,'integrity':'client_reported_preview'}
