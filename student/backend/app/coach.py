"""Bounded performance coach: deterministic fallback, optional OpenAI explanation."""
import hashlib
import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from app.auth import require_school_student, protect_mutation
from app.db import engine
from app.lessons import scope
from app.journey import snapshot

router=APIRouter(prefix='/api/v1/student/journey')
PROMPT_VERSION='performance-coach-v1'

def configured():
    return os.environ.get('STUDENT_AI_ENABLED')=='true' and bool(os.environ.get('OPENAI_API_KEY')) and bool(os.environ.get('OPENAI_MODEL'))

def context(data):
    # No name, email, membership/school IDs, raw answers or legal source text leaves the server.
    return {k:data[k] for k in ('is_demo','score','score_change','sample_size','streak','completed_sections','total_sections','days_left')} | {
        'daily_minutes':data['profile']['daily_minutes'],
        'topics':[{'title':t['title_ar'],'score':t['score'],'sample':t['sample']} for t in data['topics']]}

def fallback(data,intent):
    focus=data.get('focus')
    title=focus['title_ar'] if focus else 'أول درس'
    intro='هاد التحليل مبني على محاكاة تجريبية، ماشي نتائج امتحان حقيقية. ' if data['is_demo'] else 'ما عندناش نتائج مصححة كافية باش نحكمو على المستوى ديالك. '
    if intent=='plan': return intro+f"خصص {data['profile']['daily_minutes']} دقيقة اليوم: بدا بمراجعة {title}، ومن بعدها جرّب سلسلة. سجل شنو ما فهمتيش باش ترجع ليه مع الأستاذ."
    if intent=='motivation': return intro+f"كملتي {data['completed_sections']} فقرة. خذ فكرة وحدة اليوم وطبقها بشوية، والاستمرار أهم من السرعة."
    return intro+(f"المعدل التجريبي فآخر 14 يوم هو {data['score']}% من {data['sample_size']} جواب مولّد. " if data['score'] is not None else '')+f'المراجعة المقترحة دابا: {title}. هاد المؤشر ما كيضمنش النجاح فالامتحان.'

def generate(metrics,intent):
    body={'model':os.environ['OPENAI_MODEL'],'store':False,'max_output_tokens':700,
        'instructions':'You are a Moroccan Darija study-performance coach. Reply in Darija, at most 150 words. Use only supplied aggregate metrics. Never grade answers, give traffic/legal rules, infer pass probability or promise exam readiness. Missing scores mean unknown. If is_demo is true explicitly label ALL performance scores synthetic. Give 2 concrete study actions, kind and concise. No tools or external actions.',
        'input':json.dumps({'intent':intent,'metrics':metrics},ensure_ascii=False)}
    req=Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
    with urlopen(req,timeout=20) as r:
        result=json.loads(r.read(262145))
    if result.get('status')!='completed': raise ValueError('Incomplete provider response')
    answer='\n'.join(part['text'] for item in result.get('output',[]) if item.get('type')=='message' for part in item.get('content',[]) if part.get('type')=='output_text')
    if not answer.strip() or len(answer)>6000: raise ValueError('Invalid provider response')
    return answer,result.get('usage',{})

class CoachRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    intent:Literal['analysis','plan','motivation']='analysis'

@router.post('/coach',dependencies=[Depends(protect_mutation)])
def coach(body:CoachRequest,response:Response,user=Depends(require_school_student)):
    response.headers['Cache-Control']='no-store'
    data=snapshot(user)
    result={'source':'rules','reason':'not_configured','answer':fallback(data,body.intent),'prompt_version':PROMPT_VERSION}
    if not configured(): return result
    metrics=context(data); model=os.environ['OPENAI_MODEL']
    digest=hashlib.sha256(json.dumps([PROMPT_VERSION,model,metrics],sort_keys=True,default=str).encode()).hexdigest()
    run=uuid4()
    with engine.begin() as c:
        scope(c,user)
        # Database lock and persistent reservations bound paid calls even across API workers.
        c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'coach:'+str(user['membership_id'])})
        old=c.execute(text('SELECT status,answer FROM intelligence.coach_reports WHERE input_hash=:h AND intent=:i AND day=CURRENT_DATE'),{'h':digest,'i':body.intent}).mappings().first()
        if old:
            return {**result,'source':'openai' if old['status']=='complete' else 'rules','reason':'cached' if old['status']=='complete' else old['status'],'answer':old['answer'] if old['status']=='complete' else result['answer']}
        count=c.execute(text('SELECT count(*) FROM intelligence.coach_reports WHERE day=CURRENT_DATE')).scalar_one()
        if count>=3: return {**result,'reason':'daily_limit'}
        c.execute(text('INSERT INTO intelligence.coach_reports(id,tenant_id,membership_id,input_hash,intent,status,model) VALUES(:id,:t,:m,:h,:i,\'pending\',:model)'),dict(id=run,t=user['tenant_id'],m=user['membership_id'],h=digest,i=body.intent,model=model))
    try:
        answer,usage=generate(metrics,body.intent)
        status='complete'
    except Exception:
        # Never return/log upstream errors containing credentials or request payloads; no automatic retries.
        answer=None;usage={};status='failed'
    with engine.begin() as c:
        scope(c,user)
        c.execute(text('UPDATE intelligence.coach_reports SET status=:s,answer=:a,input_tokens=:it,output_tokens=:ot WHERE id=:id'),dict(id=run,s=status,a=answer,it=usage.get('input_tokens'),ot=usage.get('output_tokens')))
    return {**result,'source':'openai' if answer else 'rules','reason':status,'answer':answer or result['answer']}
