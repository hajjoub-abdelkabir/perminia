"""School MVP. Session-authenticated DB boundary, no tenant IDs from clients."""
import json
import secrets
from datetime import date
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from app.auth import COOKIE, token_hash, protect_mutation, require_account, LoginInput
from app.db import engine
from app.student import preview_enabled

router=APIRouter(prefix='/api/v1/school',dependencies=[Depends(require_account),Depends(preview_enabled)])

def call(request,action,data=None,support=False):
    with engine.begin() as c:
        result=c.execute(text('SELECT '+('identity.account_support' if support else 'identity.school_portal')+'(:session,:action,CAST(:data AS jsonb))'),
          {'session':token_hash(request.cookies.get(COOKIE,'')),'action':action,'data':json.dumps(data or {},default=str)}).scalar_one()
    if 'error' in result:
        code=result['error']
        if support and code==409:raise HTTPException(409,'تبدلات حالة الدعوة أو الحساب. حدّث اللائحة وعاود جرّب.')
        raise HTTPException(code,{401:'دخل للحساب ديالك من جديد.',403:'ما عندكش الصلاحية لهاد العملية.',404:'هاد العنصر ما متاحش فالحساب ديالك.',409:'الحالة تبدلات أو الطلب موجود من قبل. حدّث الصفحة؛ إنجاز المهمة خاصو قراءة كاملة أو جولة جديدة محفوظة.',422:'راجع المعطيات اللي دخلتي.'}.get(code,'تعذر حفظ الطلب.'))
    return result

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Student(Input):
    student_id:UUID
class Link(Student):
    teacher_id:UUID|None
    expected_link_id:UUID|None
class Status(Student):
    status:Literal['active','inactive']
class Assignment(Student):
    kind:Literal['lesson','series']
    target_id:UUID
    note:str=Field(default='',max_length=400)
    due_on:date|None=None
class Task(Input):
    task_id:UUID
class Cancel(Student):
    task_id:UUID
class Invite(Input):
    email:str=Field(min_length=3,max_length=254)
    role:Literal['student','instructor']
    @field_validator('email')
    @classmethod
    def email_valid(cls,v):return LoginInput.normalize_email(v)

@router.get('/roster')
def roster(request:Request):return call(request,'roster')
@router.get('/students/{student_id}')
def detail(student_id:UUID,request:Request):return call(request,'detail',{'student_id':student_id})
@router.get('/my-tasks')
def tasks(request:Request):return call(request,'my_tasks')
@router.post('/link',dependencies=[Depends(protect_mutation)])
def link(body:Link,request:Request):return call(request,'link',body.model_dump())
@router.post('/status',dependencies=[Depends(protect_mutation)])
def status(body:Status,request:Request):return call(request,'status',body.model_dump())
@router.post('/assign',dependencies=[Depends(protect_mutation)])
def assign(body:Assignment,request:Request):return call(request,'assign',body.model_dump())
@router.post('/complete',dependencies=[Depends(protect_mutation)])
def complete(body:Task,request:Request):return call(request,'complete',body.model_dump())
@router.post('/cancel',dependencies=[Depends(protect_mutation)])
def cancel(body:Cancel,request:Request):return call(request,'cancel',body.model_dump())
@router.post('/invite',dependencies=[Depends(protect_mutation)],status_code=201)
def invite(body:Invite,request:Request):
    code=secrets.token_urlsafe(32)
    result=call(request,'invite',{**body.model_dump(),'hash':token_hash(code)})
    return {**result,'invitation_code':code,'email':body.email}


class InvitationChange(Input):
    invitation_id:UUID
    expected_version:int=Field(ge=1)
class RecoveryIssue(Input):
    membership_id:UUID
    identity_confirmed:Literal[True]

@router.get('/invitations')
def invitations(request:Request,offset:int=Query(default=0,ge=0,le=100000)):
    return call(request,'invitations',{'offset':offset},support=True)
@router.post('/invitations/renew',dependencies=[Depends(protect_mutation)])
def renew_invitation(body:InvitationChange,request:Request):
    code=secrets.token_urlsafe(32)
    result=call(request,'renew',{**body.model_dump(),'hash':token_hash(code)},support=True)
    return {**result,'invitation_code':code}
@router.post('/invitations/revoke',dependencies=[Depends(protect_mutation)])
def revoke_invitation(body:InvitationChange,request:Request):
    return call(request,'revoke',body.model_dump(),support=True)
@router.post('/recovery',dependencies=[Depends(protect_mutation)],status_code=201)
def issue_recovery(body:RecoveryIssue,request:Request):
    code=secrets.token_urlsafe(32)
    result=call(request,'recovery',{'membership_id':body.membership_id,'hash':token_hash(code)},support=True)
    return {**result,'recovery_code':code}
