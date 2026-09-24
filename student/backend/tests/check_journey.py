"""Local demo smoke test; removes only its own temporary participation record."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from uuid import uuid4
from http.cookiejar import CookieJar
from urllib.request import Request,build_opener,HTTPCookieProcessor
from urllib.error import HTTPError
from import_dataset import connect

BASE='http://api:8000/api/v1/'
def call(client,path,body=None,method=None):
    req=Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={'Content-Type':'application/json','Origin':'http://localhost:5174','X-Sya9a-Request':'student'})
    try:
        with client.open(req,timeout=15) as r:return r.status,json.load(r)
    except HTTPError as e:return e.code,json.load(e)

accounts=[a for a in json.loads(Path('/seed-output/accounts.json').read_text())['accounts'] if a['role']=='student'][:4]
summaries=[];clients=[]
for a in accounts:
    client=build_opener(HTTPCookieProcessor(CookieJar()));clients.append(client)
    status,_=call(client,'auth/login',{'email':a['email'],'password':a['password']});assert status==200
    status,d=call(client,'student/journey');assert status==200 and d['is_demo']
    summaries.append({'persona':d['profile']['persona'],'observations':d['demo_sessions'],'score':d['score']})
assert len({s['persona'] for s in summaries})==4
client=clients[0];session=uuid4()
try:
    _,series=call(client,'student/preview/series')
    _,data=call(client,'student/preview/series/'+series['items'][0]['id'])
    body={'series_id':data['series']['id'],'outcomes':[{'revision_id':q['revision_id'],'status':'skipped','choices':[]} for q in data['questions']]}
    route='student/journey/sessions/'+str(session)
    for _ in range(2):assert call(client,route,body,'PUT')[0]==200
    _,d=call(client,'student/journey');assert sum(s['id']==str(session) for s in d['real_sessions'])==1
    assert all(s['id']!=str(session) for s in call(clients[1],'student/journey')[1]['real_sessions'])
    other={**body,'outcomes':[dict(o) for o in body['outcomes']]};other['outcomes'][0]['status']='expired'
    assert call(client,route,other,'PUT')[0]==409
    invalid={**body,'membership_id':accounts[1]['membership_id']}
    assert call(client,route,invalid,'PUT')[0]==422
    assert call(client,route,{**body,'outcomes':body['outcomes'][:-1]},'PUT')[0]==422
    assert call(build_opener(),'student/journey')[0]==401
finally:
    with connect() as c:
        c.execute('DELETE FROM learning.preview_sessions WHERE id=%s AND membership_id=%s',(session,accounts[0]['membership_id']))
    for client in clients:call(client,'auth/logout',{})
print(json.dumps({'profiles':summaries,'participation':'persisted, idempotent, isolated; test record cleaned'},ensure_ascii=False))
