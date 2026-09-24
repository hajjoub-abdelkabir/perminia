CREATE TABLE identity.local_accounts (
 membership_id uuid PRIMARY KEY REFERENCES identity.memberships,
 email text NOT NULL UNIQUE CHECK(email=lower(email) AND length(email)<=254),
 display_name text NOT NULL CHECK(length(display_name) BETWEEN 2 AND 80),
 password_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE identity.local_sessions (
 token_hash text PRIMARY KEY CHECK(length(token_hash)=64),
 membership_id uuid NOT NULL REFERENCES identity.local_accounts,
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT now()+interval '7 days'
);
CREATE INDEX local_sessions_member_idx ON identity.local_sessions(membership_id);
CREATE INDEX local_sessions_expiry_idx ON identity.local_sessions(expires_at);
CREATE TABLE identity.auth_limits (
 bucket text PRIMARY KEY CHECK(length(bucket)=64),
 window_start timestamptz NOT NULL DEFAULT now(),
 hits integer NOT NULL CHECK(hits>0)
);
-- A dedicated tenant for self-registered students, never an instructor/admin tenant.
INSERT INTO identity.tenants(id,name) VALUES ('21f7b3b4-53e9-40fc-9144-bb82d634b318','التلاميذ المستقلون');

CREATE FUNCTION identity.auth_rate_limit(p_bucket text, p_limit integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE n integer;
BEGIN
 INSERT INTO identity.auth_limits(bucket,hits) VALUES(p_bucket,1)
 ON CONFLICT(bucket) DO UPDATE SET
  hits=CASE WHEN identity.auth_limits.window_start<now()-interval '15 minutes' THEN 1 ELSE identity.auth_limits.hits+1 END,
  window_start=CASE WHEN identity.auth_limits.window_start<now()-interval '15 minutes' THEN now() ELSE identity.auth_limits.window_start END
 RETURNING hits INTO n;
 DELETE FROM identity.auth_limits WHERE window_start<now()-interval '1 day';
 RETURN n<=p_limit;
END $$;

CREATE FUNCTION identity.auth_register(p_email text,p_name text,p_password text,p_token text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE u uuid; m uuid; t uuid='21f7b3b4-53e9-40fc-9144-bb82d634b318';
BEGIN
 INSERT INTO identity.users(auth_subject) VALUES('local:'||gen_random_uuid()::text) RETURNING id INTO u;
 INSERT INTO identity.memberships(tenant_id,user_id,role) VALUES(t,u,'student') RETURNING id INTO m;
 INSERT INTO identity.learner_profiles(membership_id,tenant_id,category_id) VALUES(m,t,'B');
 INSERT INTO identity.local_accounts(membership_id,email,display_name,password_hash) VALUES(m,p_email,p_name,p_password);
 INSERT INTO identity.local_sessions(token_hash,membership_id) VALUES(p_token,m);
 RETURN m;
END $$;

CREATE FUNCTION identity.auth_credentials(p_email text)
RETURNS TABLE(membership_id uuid,password_hash text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT a.membership_id,a.password_hash FROM identity.local_accounts a
 JOIN identity.memberships m ON m.id=a.membership_id
 JOIN identity.tenants t ON t.id=m.tenant_id
 WHERE a.email=p_email AND m.status='active' AND m.role='student' AND t.status='active'
$$;

CREATE FUNCTION identity.auth_new_session(p_member uuid,p_hash text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id WHERE m.id=p_member AND m.status='active' AND m.role='student' AND t.status='active') THEN
  RAISE EXCEPTION 'Inactive student';
 END IF;
 -- Serialise concurrent logins, keep at most ten active sessions per student.
 PERFORM 1 FROM identity.local_accounts WHERE membership_id=p_member FOR UPDATE;
 DELETE FROM identity.local_sessions WHERE expires_at<=now();
 DELETE FROM identity.local_sessions WHERE token_hash IN (
   SELECT token_hash FROM identity.local_sessions WHERE membership_id=p_member ORDER BY created_at DESC OFFSET 9
 );
 INSERT INTO identity.local_sessions(token_hash,membership_id) VALUES(p_hash,p_member);
END $$;

CREATE FUNCTION identity.auth_session(p_hash text)
RETURNS TABLE(membership_id uuid,tenant_id uuid,display_name text,email text,category_id text,preferred_locale text,created_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT a.membership_id,m.tenant_id,a.display_name,a.email,p.category_id,p.preferred_locale,a.created_at
 FROM identity.local_sessions s JOIN identity.local_accounts a ON a.membership_id=s.membership_id
 JOIN identity.memberships m ON m.id=a.membership_id
 JOIN identity.tenants t ON t.id=m.tenant_id
 JOIN identity.learner_profiles p ON p.membership_id=m.id
 WHERE s.token_hash=p_hash AND s.expires_at>now() AND m.status='active' AND m.role='student' AND t.status='active'
$$;

CREATE FUNCTION identity.auth_logout(p_hash text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 DELETE FROM identity.local_sessions WHERE token_hash=p_hash
$$;

REVOKE ALL ON identity.local_accounts,identity.local_sessions,identity.auth_limits FROM PUBLIC,sya9a_student_runtime;
REVOKE ALL ON FUNCTION identity.auth_rate_limit(text,integer),identity.auth_register(text,text,text,text),identity.auth_credentials(text),identity.auth_new_session(uuid,text),identity.auth_session(text),identity.auth_logout(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.auth_rate_limit(text,integer),identity.auth_register(text,text,text,text),identity.auth_credentials(text),identity.auth_new_session(uuid,text),identity.auth_session(text),identity.auth_logout(text) TO sya9a_student_runtime;
