"""Conservative, explainable initial policy. No success-probability prediction."""
from collections import defaultdict
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import hashlib

VERSION='mastery-evidence-v1'
TZ=ZoneInfo('Africa/Casablanca')

def summarize(evidence,now=None):
    now=now or datetime.now(TZ)
    # First encounter per family/day prevents drilling the same answer from inflating evidence.
    first={}
    for e in sorted(evidence,key=lambda e:e['received_at']):
        if not now-timedelta(days=30)<=e['received_at']<=now:continue
        day=e['received_at'].astimezone(TZ).date()
        for concept in e['concepts']:
            key=(str(concept['id']),str(e['family_id']),day)
            first.setdefault(key,{**e,'concept':concept,'day':day})
    grouped=defaultdict(list)
    for (concept,_,_),e in first.items():grouped[concept].append(e)
    result=[]
    for ident,rows in grouped.items():
        families=len({str(e['family_id']) for e in rows});days=len({e['day'] for e in rows})
        score=round(100*sum(e['outcome']=='correct' for e in rows)/len(rows))
        varied=len(rows)>=6 and families>=3 and days>=2
        state='insufficient' if len(rows)<3 or families<2 else 'review' if score<60 else 'stable' if score>=80 and varied else 'developing'
        result.append({'concept_id':ident,'label':rows[0]['concept']['label'],'state':state,'score':score,
            'evidence_count':len(rows),'distinct_families':families,'days':days,'confidence':'varied' if varied else 'limited',
            'last_seen':max(e['received_at'] for e in rows),'policy_version':VERSION})
    return sorted(result,key=lambda r:(r['score'],r['label']))

def select_practice(pool,evidence,seed,limit=10):
    mastery={m['concept_id']:m for m in summarize(evidence)}
    seen={}
    for e in evidence:
        key=str(e['family_id']);seen[key]=max(seen.get(key,e['received_at']),e['received_at'])
    def rank(q):
        states=[mastery.get(str(k['id']),{}).get('state','unseen') for k in q['concepts']]
        priority=min({'review':0,'insufficient':1,'unseen':1,'developing':2,'stable':3}[s] for s in states)
        when=seen.get(str(q['family_id']))
        return priority,when.timestamp() if when else 0,hashlib.sha256((str(seed)+str(q['revision_id'])).encode()).hexdigest()
    selected=[];families=set()
    # Prefer unseen families, but reserve a portion for scheduled/weak review when available.
    ranked=sorted(pool,key=rank)
    unseen=[q for q in ranked if str(q['family_id']) not in seen]
    ordered=unseen[:max(1,limit//5)]+ranked
    for q in ordered:
        family=str(q['family_id'])
        if family in families:continue
        families.add(family)
        states=[mastery.get(str(k['id']),{}).get('state','unseen') for k in q['concepts']]
        reason='موقف جديد لقياس الفهم' if family not in seen else 'تقوية مفهوم محتاج مراجعة' if 'review' in states else 'مراجعة مفهوم سبق تعلمتيه'
        selected.append({**q,'selection_reason':reason})
        if len(selected)==limit:break
    return selected
