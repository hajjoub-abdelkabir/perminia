"""Privileged local provisioning; never imported or exposed by the HTTP app.
Run through the configure-runtime tools service (owner credentials).
Invitation codes are printed once on explicit operator request; do not log them.
"""
import argparse
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from import_dataset import connect


def create_school(connection, code, name):
    name = name.strip()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,39}', code) or not 2 <= len(name) <= 120:
        raise ValueError('Use a 3-40 character lowercase school code and a 2-120 character name.')
    # Idempotent and serialized by code; never rename a school implicitly.
    connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('school:'+code,))
    existing = connection.execute('SELECT s.tenant_id,t.name FROM identity.schools s JOIN identity.tenants t ON t.id=s.tenant_id WHERE s.code=%s',(code,)).fetchone()
    if existing:
        if existing[1] != name:
            raise ValueError('School code already exists under a different name.')
        return {'school_id': str(existing[0]), 'code': code, 'status': 'already_exists'}
    school = connection.execute('INSERT INTO identity.tenants(name) VALUES (%s) RETURNING id',(name,)).fetchone()[0]
    connection.execute('INSERT INTO identity.schools(tenant_id,code) VALUES(%s,%s)',(school,code))
    connection.execute("INSERT INTO identity.provisioning_audit(school_id,event_type,actor) VALUES(%s,'school_created',session_user)",(school,))
    return {'school_id': str(school), 'code': code, 'status': 'created'}


def invite_student(connection, code, email, expires_hours=72, role='student'):
    if role not in ('student','instructor','school_manager'):
        raise ValueError('Unsupported school role.')
    from app.auth import LoginInput
    email = LoginInput.normalize_email(email)
    if not 1 <= expires_hours <= 168:
        raise ValueError('Invitation lifetime must be between 1 and 168 hours.')
    school = connection.execute("SELECT s.tenant_id FROM identity.schools s JOIN identity.tenants t ON t.id=s.tenant_id WHERE s.code=%s AND t.status='active' FOR SHARE OF t",(code,)).fetchone()
    if not school:
        raise ValueError('Active school not found.')
    school = school[0]
    connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('invite:'+str(school)+':'+email,))
    if connection.execute('SELECT 1 FROM identity.local_accounts WHERE email=%s',(email,)).fetchone():
        raise ValueError('This email already has an account. Do not reset or reassign it via an invitation.')
    revoked = connection.execute('UPDATE identity.student_invitations SET revoked_at=clock_timestamp() WHERE school_id=%s AND email=%s AND used_at IS NULL AND revoked_at IS NULL RETURNING id',(school,email)).fetchall()
    for old in revoked:
        connection.execute("INSERT INTO identity.provisioning_audit(school_id,invitation_id,event_type,actor) VALUES(%s,%s,'invitation_revoked',session_user)",(school,old[0]))
    token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    invite = connection.execute('INSERT INTO identity.student_invitations(school_id,email,token_hash,expires_at,target_role) VALUES(%s,%s,%s,%s,%s) RETURNING id',(school,email,hashlib.sha256(token.encode()).hexdigest(),expiry,role)).fetchone()[0]
    connection.execute("INSERT INTO identity.provisioning_audit(school_id,invitation_id,event_type,actor) VALUES(%s,%s,'invitation_created',session_user)",(school,invite))
    return {'invitation_id': str(invite), 'school_code': code, 'email': email, 'expires_at': expiry.isoformat(), 'invitation_code': token}


def revoke_invitation(connection, invitation_id):
    row = connection.execute('UPDATE identity.student_invitations SET revoked_at=clock_timestamp() WHERE id=%s AND used_at IS NULL AND revoked_at IS NULL RETURNING school_id',(UUID(str(invitation_id)),)).fetchone()
    if row:
        connection.execute("INSERT INTO identity.provisioning_audit(school_id,invitation_id,event_type,actor) VALUES(%s,%s,'invitation_revoked',session_user)",(row[0],invitation_id))
    return {'status': 'revoked' if row else 'not_pending', 'invitation_id': str(invitation_id)}


def recover_account(connection,code,email):
    from app.auth import LoginInput
    email=LoginInput.normalize_email(email)
    member=connection.execute("SELECT m.id FROM identity.local_accounts a JOIN identity.memberships m ON m.id=a.membership_id JOIN identity.schools s ON s.tenant_id=m.tenant_id WHERE s.code=%s AND a.email=%s",(code,email)).fetchone()
    if not member:raise ValueError('Account not found in this school.')
    token=secrets.token_urlsafe(32)
    expiry=connection.execute('SELECT identity.issue_account_recovery(%s,%s,session_user)',(member[0],hashlib.sha256(token.encode()).hexdigest())).fetchone()[0]
    if not expiry:raise ValueError('Active school account required.')
    return {'email':email,'recovery_code':token,'expires_at':expiry.isoformat()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    school=commands.add_parser('create-school')
    school.add_argument('--code',required=True)
    school.add_argument('--name',required=True)
    invite=commands.add_parser('invite-student')
    invite.add_argument('--school-code',required=True)
    invite.add_argument('--email',required=True)
    invite.add_argument('--role',choices=['student','instructor','school_manager'],default='student')
    invite.add_argument('--expires-hours',type=int,default=72)
    revoke=commands.add_parser('revoke-invitation')
    revoke.add_argument('--id',type=UUID,required=True)
    recovery=commands.add_parser('recover-account')
    recovery.add_argument('--school-code',required=True)
    recovery.add_argument('--email',required=True)
    recovery.add_argument('--identity-confirmed',action='store_true',required=True,help='Confirm identity through an independent trusted channel before issuing a code')
    args=parser.parse_args()
    try:
        with connect() as connection:
            if args.command=='create-school': result=create_school(connection,args.code,args.name)
            elif args.command=='invite-student': result=invite_student(connection,args.school_code,args.email,args.expires_hours,args.role)
            elif args.command=='recover-account': result=recover_account(connection,args.school_code,args.email)
            else: result=revoke_invitation(connection,args.id)
        print(json.dumps(result,ensure_ascii=False))
    except ValueError as error:
        parser.exit(2, str(error)+'\n')


if __name__=='__main__':
    main()
