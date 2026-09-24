"""Assign existing demo pupils once; never alter real accounts or later reassignments."""
import os
from seed_demo import fixtures,SCHOOLS
from import_dataset import connect

def run():
    if os.environ.get('POSTGRES_DB')!='sya9a_student':raise ValueError('Local demo DB only')
    rows=fixtures();added=0
    with connect() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended('demo-school-links-v1',0))")
        for code,_,_,_ in SCHOOLS:
            group=[x for x in rows if x['school']==code]
            manager=next(x for x in group if x['role']=='school_manager')
            teachers=[x for x in group if x['role']=='instructor']
            for n,student in enumerate(x for x in group if x['role']=='student'):
                # Verify synthetic identity provenance instead of relying on email naming.
                for a in [student,manager,teachers[n%len(teachers)]]:
                    found=c.execute('SELECT m.tenant_id FROM identity.memberships m JOIN identity.users u ON u.id=m.user_id JOIN identity.schools s ON s.tenant_id=m.tenant_id WHERE m.id=%s AND u.auth_subject=%s AND s.code=%s AND m.role=%s',(a['membership_id'],a['subject'],code,a['role'])).fetchone()
                    if not found:raise ValueError('Missing or changed demo identity')
                result=c.execute("INSERT INTO identity.school_student_links(tenant_id,student_id,teacher_id,assigned_by) SELECT %s,%s,%s,%s WHERE NOT EXISTS(SELECT 1 FROM identity.school_student_links WHERE student_id=%s) ON CONFLICT DO NOTHING",(found[0],student['membership_id'],teachers[n%len(teachers)]['membership_id'],manager['membership_id'],student['membership_id']))
                added+=result.rowcount
    print({'demo_links_added':added})
if __name__=='__main__':run()
