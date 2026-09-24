"""Idempotent synthetic learning trajectories, restricted to existing demo students."""
from datetime import datetime, timedelta, timezone
from uuid import uuid5
import json
import os
from seed_demo import NS, fixtures
from import_dataset import connect

VERSION='perminia-journey-demo-v1'
ANCHOR=datetime(2026,9,14,12,tzinfo=timezone.utc)
PERSONAS=['تطور مستمر','قريب من موعد الامتحان','خاصو يرجع للإيقاع','بداية الرحلة']

def run():
    if os.environ.get('POSTGRES_DB')!='sya9a_student': raise ValueError('Local demo database only')
    inserted=0
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(VERSION,))
        lessons=c.execute('SELECT id FROM content.preview_lessons ORDER BY position').fetchall()
        if len(lessons)!=10: raise ValueError('Expected imported 10-lesson demo curriculum')
        for index,a in enumerate(x for x in fixtures() if x['role']=='student'):
            member=c.execute('''SELECT m.tenant_id,m.id FROM identity.memberships m JOIN identity.users u ON u.id=m.user_id
              WHERE m.id=%s AND m.role='student' AND u.auth_subject=%s''',(a['membership_id'],a['subject'])).fetchone()
            if not member: raise ValueError('Run/verify seed_demo.py first')
            tenant,mid=member;variant=index%4
            enrolled=(ANCHOR-timedelta(days=3 if variant==3 else 42)).date()
            exam=(ANCHOR+timedelta(days=[28,7,35,60][variant])).date()
            c.execute('''INSERT INTO learning.journey_profiles(tenant_id,membership_id,enrolled_on,exam_on,daily_minutes,fixture_version,persona)
             VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,membership_id) DO UPDATE
             SET fixture_version=excluded.fixture_version,persona=excluded.persona,enrolled_on=excluded.enrolled_on,
                 exam_on=coalesce(journey_profiles.exam_on,excluded.exam_on)
             WHERE journey_profiles.fixture_version IS NULL''',(tenant,mid,enrolled,exam,[20,30,15,10][variant],VERSION,PERSONAS[variant]))
            for n in range([28,36,15,2][variant]):
                day= (27-n) if variant==0 else (35-n) if variant==1 else (38-2*n) if variant==2 else (2-n)
                rate= min(9,3+n//5) if variant==0 else 8+(n%3==0) if variant==1 else 4+(n%3) if variant==2 else 3+n
                correct=max(0,min(10,rate+((n+index)%3-1)))
                ident=uuid5(NS,VERSION+':'+str(mid)+':'+str(n))
                row=c.execute('''INSERT INTO learning.demo_performance(id,tenant_id,membership_id,fixture_version,occurred_at,lesson_id,correct,total,minutes)
                 VALUES(%s,%s,%s,%s,%s,%s,%s,10,%s) ON CONFLICT DO NOTHING RETURNING id''',
                 (ident,tenant,mid,VERSION,ANCHOR-timedelta(days=day),lessons[n%10][0],correct,10+n%8)).fetchone()
                inserted+=bool(row)
    print(json.dumps({'fixture_version':VERSION,'inserted_observations':inserted,'students':47,'personas':4,'anchor':ANCHOR.date().isoformat()}))

if __name__=='__main__':run()
