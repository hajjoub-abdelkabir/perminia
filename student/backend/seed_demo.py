"""Explicit local demo fixtures. No updates, resets, published questions or fake results."""
import argparse
import json
import os
import secrets
from pathlib import Path
from uuid import UUID, uuid5

from app.auth import password_hash, password_matches
from import_dataset import connect
from provision_school import create_school

VERSION = 'perminia-demo-v1'
NS = UUID('aa4387be-2d23-48c4-ac2a-45d112cc30e3')
SCHOOLS = [
    ('demo-rabat', 'مدرسة الرباط التجريبية', 5, 1),
    ('demo-casa', 'مدرسة الدار البيضاء التجريبية', 12, 2),
    ('demo-marrakech', 'مدرسة مراكش التجريبية', 30, 3),
]
NAMES = ['أمين', 'سلمى', 'ياسين', 'مريم', 'أيوب', 'هاجر', 'حمزة', 'إيمان', 'عثمان', 'سارة']


def fixtures():
    rows = []
    for school, _, students, teachers in SCHOOLS:
        for role, count, label in [('school_manager', 1, 'مدير'), ('instructor', teachers, 'أستاذ'), ('student', students, 'تلميذ')]:
            for number in range(1, count + 1):
                key = f'{school}:{role}:{number}'
                rows.append(dict(school=school, role=role,
                    email=f'{role}.{number:02}@{school}.example.test',
                    name=f'{NAMES[(number-1) % len(NAMES)]} — {label} تجريبي {number:02}',
                    user_id=str(uuid5(NS, key + ':user')),
                    membership_id=str(uuid5(NS, key + ':member')),
                    subject=VERSION + ':' + key))
    return rows


def run(path, verify=False):
    if os.environ.get('POSTGRES_DB') != 'sya9a_student':
        raise ValueError('This fixture is restricted to the local sya9a_student database.')
    rows = fixtures()
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (VERSION,))
        if path.exists():
            manifest = json.loads(path.read_text(encoding='utf-8'))
            if manifest['version'] != VERSION or [{k:v for k,v in a.items() if k != 'password'} for a in manifest['accounts']] != rows:
                raise ValueError('Demo manifest mismatch; no accounts changed.')
        else:
            if verify or c.execute('SELECT 1 FROM identity.users WHERE auth_subject LIKE %s', (VERSION + ':%',)).fetchone():
                raise ValueError('Original credential manifest required; passwords will not be reset.')
            manifest = {'version': VERSION, 'accounts': [dict(r, password=secrets.token_urlsafe(24)) for r in rows]}
            path.parent.mkdir(parents=True, exist_ok=True)
            # Save before committing DB data so a lost terminal never loses credentials.
            with path.open('x', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        created = 0
        for code, name, _, _ in SCHOOLS:
            if not verify:
                create_school(c, code, name)
            school = c.execute('SELECT s.tenant_id,t.name,t.status FROM identity.schools s JOIN identity.tenants t ON t.id=s.tenant_id WHERE s.code=%s', (code,)).fetchone()
            if not school or school[1:] != (name, 'active'):
                raise ValueError('School fixture mismatch; no records overwritten.')
            for account in (a for a in manifest['accounts'] if a['school'] == code):
                existing = c.execute('''SELECT a.membership_id,m.tenant_id,m.role,u.id,u.auth_subject,a.display_name,a.password_hash,m.status
                    FROM identity.local_accounts a JOIN identity.memberships m ON m.id=a.membership_id
                    JOIN identity.users u ON u.id=m.user_id WHERE a.email=%s''', (account['email'],)).fetchone()
                if not existing:
                    if verify:
                        raise ValueError('Missing demo account.')
                    c.execute('INSERT INTO identity.users(id,auth_subject) VALUES(%s,%s)', (account['user_id'],account['subject']))
                    c.execute('INSERT INTO identity.memberships(id,tenant_id,user_id,role) VALUES(%s,%s,%s,%s)',
                        (account['membership_id'],school[0],account['user_id'],account['role']))
                    c.execute('INSERT INTO identity.local_accounts(membership_id,email,display_name,password_hash) VALUES(%s,%s,%s,%s)',
                        (account['membership_id'],account['email'],account['name'],password_hash(account['password'])))
                    if account['role'] == 'student':
                        c.execute("INSERT INTO identity.learner_profiles(membership_id,tenant_id,category_id) VALUES(%s,%s,'B')", (account['membership_id'],school[0]))
                    created += 1
                else:
                    expected = (account['membership_id'],str(school[0]),account['role'],account['user_id'],account['subject'],account['name'])
                    if tuple(map(str,existing[:6])) != expected or existing[7] != 'active' or not password_matches(account['password'],existing[6]):
                        raise ValueError('Existing account differs; never reset or reassign it.')
                profiles = c.execute('SELECT tenant_id,category_id,preferred_locale FROM identity.learner_profiles WHERE membership_id=%s', (account['membership_id'],)).fetchall()
                expected_profiles = [(school[0],'B','ary-MA')] if account['role']=='student' else []
                if profiles != expected_profiles:
                    raise ValueError('Learner profile isolation mismatch.')
                eligible = c.execute('SELECT membership_id FROM identity.auth_credentials(%s)', (account['email'],)).fetchall()
                if bool(eligible) != (account['role']=='student'):
                    raise ValueError('Student login role boundary failed.')
    print(json.dumps({'version':VERSION, 'created_accounts':created, 'verified_accounts':len(rows),
        'schools':[{'code':s,'students':n,'instructors':t,'managers':1} for s,_,n,t in SCHOOLS]}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    run(args.credentials, args.verify)
