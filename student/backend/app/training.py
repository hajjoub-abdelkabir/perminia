"""Server-clock practice, frozen delivery, resume and reviewed-only adaptive learning."""
import json
from datetime import timedelta
from uuid import UUID,uuid4
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Response
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import text
from app.db import engine
from app.auth import require_school_student,protect_mutation
from app.lessons import scope
from app.student import preview_enabled
from app.mastery import summarize,select_practice

router=APIRouter(prefix='/api/v1/student/training',dependencies=[Depends(require_school_student)])
def query(c,sql,**kw):return c.execute(text(sql),kw)
def clock(c):return query(c,'SELECT clock_timestamp()').scalar_one()
def lock(c,run):
    row=query(c,'SELECT * FROM learning.training_runs WHERE id=:id FOR UPDATE',id=run).mappings().first()
    if not row:raise HTTPException(404,'الجولة ما تلقاتش.')
    return dict(row)
def evidence(c):
    return [dict(r) for r in query(c,"""SELECT e.*,p.family_id,p.concepts FROM learning.training_evidence e
     JOIN (SELECT DISTINCT revision_id,family_id,concepts FROM content.training_pool WHERE status='published') p ON p.revision_id=e.revision_id
     WHERE received_at>=now()-interval '30 days' AND e.status='answered' ORDER BY received_at""").mappings()]
def finish_item(c,item,status):
    choices=item['draft_choices'] if status=='answered' else []
    query(c,'INSERT INTO learning.training_answers(item_id,tenant_id,membership_id,status,choices) VALUES(:id,:t,:m,:s,:ch)',
          id=item['id'],t=item['tenant_id'],m=item['membership_id'],s=status,ch=choices)
    query(c,'SELECT learning.evaluate_training_answer(:id)',id=item['id'])
def advance(c,run):
    """Expire elapsed slots, including time spent offline. Never restart an old deadline."""
    if run['state']!='active':return None
    cursor=None
    for item in query(c,'SELECT i.* FROM learning.training_items i LEFT JOIN learning.training_answers a ON a.item_id=i.id WHERE i.run_id=:id AND a.item_id IS NULL ORDER BY i.position',id=run['id']).mappings():
        item=dict(item)
        if item['deadline'] is None:
            start=cursor or clock(c)
            item['started_at']=start;item['deadline']=start+timedelta(seconds=30)
            query(c,'UPDATE learning.training_items SET started_at=:s,deadline=:d WHERE id=:id',s=start,d=item['deadline'],id=item['id'])
        if clock(c)<item['deadline']:return item
        finish_item(c,item,'expired');cursor=item['deadline']
    query(c,"UPDATE learning.training_runs SET state='completed',closed_at=clock_timestamp() WHERE id=:id",id=run['id'])
    run['state']='completed'
    return None
def document(c,run,current=None):
    answers=[dict(r) for r in query(c,'SELECT i.id,i.position,a.status,a.outcome FROM learning.training_items i LEFT JOIN learning.training_answers a ON a.item_id=i.id WHERE run_id=:id ORDER BY position',id=run['id']).mappings()]
    complete=run['state']=='completed'
    if not complete:
        for a in answers:a.pop('outcome',None)
    review=[]
    if complete:
        feedback={r['item_id']:dict(r) for r in query(c,'SELECT * FROM learning.training_feedback(:id)',id=run['id']).mappings()}
        for r in query(c,'SELECT i.id,i.position,i.payload,i.gradable,a.status,a.choices,a.outcome FROM learning.training_items i JOIN learning.training_answers a ON a.item_id=i.id WHERE run_id=:id ORDER BY position',id=run['id']).mappings():
            item=dict(r);f=feedback.get(item['id']);item['feedback']=f
            if item['gradable'] and not f:item['outcome']='disputed'
            review.append(item)
    graded=[r for r in review if r['outcome'] in ('correct','wrong','unanswered')]
    return {'id':run['id'],'mode':run['mode'],'state':run['state'],'title':run['title'],'server_now':clock(c),
        'total':len(answers),'answers':answers,'current':({'id':current['id'],'position':current['position'],'deadline':current['deadline'],
         'draft_choices':current['draft_choices'],'selection_version':current['selection_version'],'question':current['payload'],
         'reason':current['selection_reason'],'gradable':current['gradable']} if current else None),
        'review':review,'score':sum(r['outcome']=='correct' for r in graded) if graded else None,'graded_count':len(graded),
        'score_complete':bool(graded) and len(graded)==len(review),'policy':'training-v1'}

class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID
    mode:Literal['preview','adaptive']='preview'
    series_id:UUID|None=None

@router.post('',dependencies=[Depends(protect_mutation)])
def start(body:Start,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user)
        query(c,'SELECT pg_advisory_xact_lock(hashtextextended(:k,0))',k='training:'+str(user['membership_id']))
        existing=query(c,"SELECT * FROM learning.training_runs WHERE request_id=:request OR state='active' ORDER BY (request_id=:request) DESC LIMIT 1 FOR UPDATE",request=body.request_id).mappings().first()
        if existing:
            run=dict(existing)
            if run['mode']!=body.mode or run['series_id']!=body.series_id:raise HTTPException(409,'عندك جولة جارية. رجع ليها أو إنهِيها قبل بداية وحدة أخرى.')
            return document(c,run,advance(c,run))
        runid=uuid4();assessment=None
        if body.mode=='preview':
            preview_enabled()
            if not body.series_id:raise HTTPException(422,'اختار السلسلة.')
            series=query(c,'SELECT * FROM content.preview_series WHERE id=:id',id=body.series_id).mappings().first()
            if not series:raise HTTPException(404,'السلسلة ما تلقاتش.')
            title=series['title'];assessment=series['revision_id']
            selected=[{**dict(r),'selection_reason':'تدريب على السلسلة المختارة'} for r in query(c,'SELECT * FROM content.training_pool WHERE series_id=:id ORDER BY position',id=body.series_id).mappings()]
        else:
            if body.series_id:raise HTTPException(422,'التدريب الموجّه ما كيحتاجش سلسلة.')
            pool=[dict(r) for r in query(c,"SELECT DISTINCT ON(revision_id) * FROM content.training_pool WHERE status='published' AND jsonb_array_length(concepts)>0 ORDER BY revision_id").mappings()]
            selected=select_practice(pool,evidence(c),runid)
            if len(selected)<5:raise HTTPException(409,'التدريب الموجّه كيحتاج على الأقل 5 عائلات أسئلة معتمدة ومربوطة بالمفاهيم. المراجعة ما كملاتش بعد.')
            title='تدريبي اليوم'
        if not selected:raise HTTPException(409,'ما كايناش أسئلة متاحة.')
        query(c,'INSERT INTO learning.training_runs(id,tenant_id,membership_id,request_id,mode,series_id,assessment_revision_id,title) VALUES(:id,:t,:m,:request,:mode,:series,:rev,:title)',
              id=runid,t=user['tenant_id'],m=user['membership_id'],request=body.request_id,mode=body.mode,series=body.series_id,rev=assessment,title=title)
        for pos,q in enumerate(selected,1):
            media=[{'role':r['role'],'url':'/api/v1/student/preview/media/'+str(r['asset_id'])} for r in query(c,'SELECT asset_id,role FROM content.preview_media WHERE revision_id=:id ORDER BY position',id=q['revision_id']).mappings()]
            payload={k:q[k] for k in ('revision_id','prompt','choices','groups','response_type','family_id','concepts')};payload['media']=media
            query(c,'INSERT INTO learning.training_items(id,run_id,tenant_id,membership_id,position,revision_id,payload,gradable,selection_reason) VALUES(:id,:run,:t,:m,:pos,:rev,CAST(:payload AS jsonb),:grade,:reason)',
                id=uuid4(),run=runid,t=user['tenant_id'],m=user['membership_id'],pos=pos,rev=q['revision_id'],payload=json.dumps(payload,default=str,ensure_ascii=False),grade=q['status']=='published',reason=q['selection_reason'])
        run=lock(c,runid)
        return document(c,run,advance(c,run))

@router.get('')
def listing(response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user)
        for row in query(c,"SELECT id FROM learning.training_runs WHERE state='active'").all():
            run=lock(c,row.id);advance(c,run)
        items=[dict(r) for r in query(c,'SELECT id,title,mode,state,created_at,closed_at FROM learning.training_runs ORDER BY created_at DESC LIMIT 30').mappings()]
        pool=query(c,"SELECT count(DISTINCT family_id) FROM content.training_pool WHERE status='published' AND jsonb_array_length(concepts)>0").scalar_one()
        return {'items':items,'mastery':summarize(evidence(c)),'adaptive_available':pool>=5,'reviewed_families':pool,'policy':'mastery-evidence-v1'}

@router.get('/{run_id}')
def resume(run_id:UUID,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user);run=lock(c,run_id)
        return document(c,run,advance(c,run))

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_id:UUID
    expected_version:int=Field(ge=0)
    choices:list[UUID]=Field(max_length=20)

@router.put('/{run_id}/selection',dependencies=[Depends(protect_mutation)])
def selection(run_id:UUID,body:Selection,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user);run=lock(c,run_id);item=advance(c,run)
        if not item or item['id']!=body.item_id:return {**document(c,run,item),'notice':'سالا وقت السؤال؛ الاختيار المتأخر ما تحفظش.'}
        allowed={str(x['id']) for x in item['payload']['choices']};chosen=set(map(str,body.choices))
        if len(chosen)!=len(body.choices) or not chosen<=allowed:raise HTTPException(422,'اختيارات السؤال غير مطابقة.')
        if body.expected_version!=item['selection_version']:
            if chosen==set(map(str,item['draft_choices'])):return document(c,run,item)
            raise HTTPException(409,'الاختيارات تبدلات من نافذة أخرى. حدّث الجولة.')
        item['draft_choices']=body.choices;item['selection_version']+=1
        query(c,'UPDATE learning.training_items SET draft_choices=:ch,selection_version=:v WHERE id=:id',ch=body.choices,v=item['selection_version'],id=item['id'])
        return document(c,run,item)

class Answer(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_id:UUID
    action:Literal['confirm','skip','timeout']
    expected_version:int|None=Field(default=None,ge=0)

@router.post('/{run_id}/answer',dependencies=[Depends(protect_mutation)])
def answer(run_id:UUID,body:Answer,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user);run=lock(c,run_id)
        belongs=query(c,'SELECT 1 FROM learning.training_items WHERE id=:item AND run_id=:run',item=body.item_id,run=run_id).first()
        if not belongs:raise HTTPException(404,'السؤال ما كاينش فالجولة.')
        item=advance(c,run)
        if not item or item['id']!=body.item_id:
            return document(c,run,item)
        if body.action=='timeout':return document(c,run,item)
        if body.action=='confirm' and body.expected_version!=item['selection_version']:
            raise HTTPException(409,'الاختيارات تبدلات. استرجع الحالة المحفوظة وتأكد منها قبل التأكيد.')
        if body.action=='confirm' and not item['draft_choices']:raise HTTPException(422,'اختار جواب قبل التأكيد.')
        finish_item(c,item,'answered' if body.action=='confirm' else 'skipped')
        return document(c,run,advance(c,run))

@router.post('/{run_id}/abandon',dependencies=[Depends(protect_mutation)])
def abandon(run_id:UUID,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    with engine.begin() as c:
        scope(c,user);run=lock(c,run_id);advance(c,run)
        if run['state']=='active':query(c,"UPDATE learning.training_runs SET state='abandoned',closed_at=clock_timestamp() WHERE id=:id",id=run_id)
    return {'saved':True}
