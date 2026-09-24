CREATE TABLE identity.schools (
 tenant_id uuid PRIMARY KEY REFERENCES identity.tenants,
 code text NOT NULL UNIQUE CHECK(code ~ '^[a-z0-9][a-z0-9-]{2,39}$'),
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE identity.memberships DROP CONSTRAINT memberships_role_check;
ALTER TABLE identity.memberships ADD CONSTRAINT memberships_role_check
 CHECK(role IN ('student','reviewer','instructor','admin','school_manager'));

CREATE TABLE identity.student_invitations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 school_id uuid NOT NULL REFERENCES identity.schools(tenant_id),
 email text NOT NULL CHECK(email=lower(email) AND length(email)<=254),
 token_hash text NOT NULL UNIQUE CHECK(length(token_hash)=64),
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL CHECK(expires_at>created_at),
 used_at timestamptz,
 revoked_at timestamptz,
 membership_id uuid REFERENCES identity.memberships,
 CHECK((used_at IS NULL)=(membership_id IS NULL))
);
CREATE UNIQUE INDEX pending_school_invite_idx ON identity.student_invitations(school_id,email)
 WHERE used_at IS NULL AND revoked_at IS NULL;
CREATE INDEX invitation_expiry_idx ON identity.student_invitations(expires_at) WHERE used_at IS NULL;

CREATE TABLE identity.provisioning_audit (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 school_id uuid REFERENCES identity.schools(tenant_id),
 invitation_id uuid REFERENCES identity.student_invitations,
 membership_id uuid REFERENCES identity.memberships,
 event_type text NOT NULL CHECK(event_type IN ('school_created','invitation_created','invitation_revoked','student_activated')),
 actor text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON identity.schools,identity.student_invitations,identity.provisioning_audit FROM PUBLIC,sya9a_student_runtime;

-- Disable the old database registration entry point as well as the HTTP route.
REVOKE ALL ON FUNCTION identity.auth_register(text,text,text,text) FROM PUBLIC,sya9a_student_runtime;
DROP FUNCTION identity.auth_register(text,text,text,text);

CREATE FUNCTION identity.auth_activate(p_invite text,p_email text,p_name text,p_password text,p_session text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE i identity.student_invitations; u uuid; m uuid;
BEGIN
 SELECT * INTO i FROM identity.student_invitations WHERE token_hash=p_invite FOR UPDATE;
 IF NOT FOUND OR i.used_at IS NOT NULL OR i.revoked_at IS NOT NULL OR i.expires_at<=clock_timestamp() OR i.email<>p_email THEN
  RETURN NULL;
 END IF;
 PERFORM 1 FROM identity.schools s JOIN identity.tenants t ON t.id=s.tenant_id
 WHERE s.tenant_id=i.school_id AND t.status='active' FOR SHARE OF t;
 IF NOT FOUND THEN RETURN NULL; END IF;
 -- A duplicate email fails atomically, without consuming its invitation or resetting credentials.
 INSERT INTO identity.users(auth_subject) VALUES('local:'||gen_random_uuid()::text) RETURNING id INTO u;
 INSERT INTO identity.memberships(tenant_id,user_id,role) VALUES(i.school_id,u,'student') RETURNING id INTO m;
 INSERT INTO identity.learner_profiles(membership_id,tenant_id,category_id) VALUES(m,i.school_id,'B');
 INSERT INTO identity.local_accounts(membership_id,email,display_name,password_hash) VALUES(m,p_email,p_name,p_password);
 INSERT INTO identity.local_sessions(token_hash,membership_id) VALUES(p_session,m);
 UPDATE identity.student_invitations SET used_at=clock_timestamp(),membership_id=m WHERE id=i.id;
 INSERT INTO identity.provisioning_audit(school_id,invitation_id,membership_id,event_type,actor)
 VALUES(i.school_id,i.id,m,'student_activated','student-invitation');
 RETURN m;
END $$;
REVOKE ALL ON FUNCTION identity.auth_activate(text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.auth_activate(text,text,text,text,text) TO sya9a_student_runtime;

DROP FUNCTION identity.auth_session(text);
CREATE FUNCTION identity.auth_session(p_hash text)
RETURNS TABLE(membership_id uuid,tenant_id uuid,display_name text,email text,category_id text,preferred_locale text,created_at timestamptz,school_id uuid,school_name text,school_code text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT a.membership_id,m.tenant_id,a.display_name,a.email,p.category_id,p.preferred_locale,a.created_at,
 s.tenant_id,CASE WHEN s.tenant_id IS NOT NULL THEN t.name ELSE NULL END,s.code
 FROM identity.local_sessions x JOIN identity.local_accounts a ON a.membership_id=x.membership_id
 JOIN identity.memberships m ON m.id=a.membership_id
 JOIN identity.tenants t ON t.id=m.tenant_id
 JOIN identity.learner_profiles p ON p.membership_id=m.id AND p.tenant_id=m.tenant_id
 LEFT JOIN identity.schools s ON s.tenant_id=m.tenant_id
 WHERE x.token_hash=p_hash AND x.expires_at>now() AND m.status='active' AND m.role='student' AND t.status='active'
$$;
REVOKE ALL ON FUNCTION identity.auth_session(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.auth_session(text) TO sya9a_student_runtime;
