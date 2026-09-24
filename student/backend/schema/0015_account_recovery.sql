ALTER TABLE identity.student_invitations ADD COLUMN version integer NOT NULL DEFAULT 1;
CREATE TABLE identity.account_recovery (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),membership_id uuid NOT NULL REFERENCES identity.local_accounts,
 token_hash text NOT NULL UNIQUE CHECK(length(token_hash)=64),created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,used_at timestamptz,revoked_at timestamptz,
 CHECK(expires_at>created_at)
);
CREATE UNIQUE INDEX pending_recovery ON identity.account_recovery(membership_id) WHERE used_at IS NULL AND revoked_at IS NULL;
CREATE TABLE identity.account_access_audit (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES identity.tenants,
 actor text NOT NULL,event text NOT NULL CHECK(event IN ('recovery_issued','password_reset','invite_renewed','invite_revoked')),
 membership_id uuid REFERENCES identity.memberships,invitation_id uuid REFERENCES identity.student_invitations,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON identity.account_recovery,identity.account_access_audit FROM PUBLIC,sya9a_student_runtime;

-- Owner-only primitive, also called by the role-checked support entry point.
CREATE FUNCTION identity.issue_account_recovery(p_member uuid,p_hash text,p_actor text) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE tenant uuid; expiry timestamptz=clock_timestamp()+interval '1 hour';
BEGIN
 SELECT m.tenant_id INTO tenant FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id
 JOIN identity.schools s ON s.tenant_id=t.id JOIN identity.local_accounts a ON a.membership_id=m.id
 WHERE m.id=p_member AND m.status='active' AND t.status='active' AND m.role IN ('student','instructor','school_manager') FOR UPDATE OF m;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE identity.account_recovery SET revoked_at=clock_timestamp() WHERE membership_id=p_member AND used_at IS NULL AND revoked_at IS NULL;
 INSERT INTO identity.account_recovery(membership_id,token_hash,expires_at) VALUES(p_member,p_hash,expiry);
 INSERT INTO identity.account_access_audit(tenant_id,actor,event,membership_id) VALUES(tenant,p_actor,'recovery_issued',p_member);
 RETURN expiry;
END $$;
REVOKE ALL ON FUNCTION identity.issue_account_recovery(uuid,text,text) FROM PUBLIC,sya9a_student_runtime;

CREATE FUNCTION identity.account_support(p_session text,p_action text,p_data jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor record; inv identity.student_invitations; target uuid; expiry timestamptz; result jsonb;
BEGIN
 SELECT * INTO actor FROM identity.portal_session(p_session);
 IF NOT FOUND THEN RETURN jsonb_build_object('error',401); END IF;
 IF actor.role<>'school_manager' OR actor.school_id IS NULL THEN RETURN jsonb_build_object('error',403); END IF;
 PERFORM 1 FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id WHERE m.id=actor.membership_id AND m.status='active' AND t.status='active' FOR SHARE OF m,t;
 IF NOT FOUND THEN RETURN jsonb_build_object('error',401); END IF;
 IF p_action='invitations' THEN
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.id),'[]') INTO result FROM (
 SELECT id,email,target_role,created_at,expires_at,version,
 CASE WHEN used_at IS NOT NULL THEN 'used' WHEN revoked_at IS NOT NULL THEN 'revoked' WHEN expires_at<=now() THEN 'expired' ELSE 'pending' END AS state
 FROM identity.student_invitations WHERE school_id=actor.tenant_id AND target_role IN ('student','instructor')
 ORDER BY created_at DESC,id LIMIT 50 OFFSET coalesce((p_data->>'offset')::integer,0)) x;
 RETURN jsonb_build_object('items',result);
 END IF;
 IF p_action='recovery' THEN
 target=(p_data->>'membership_id')::uuid;
 IF NOT EXISTS(SELECT 1 FROM identity.memberships WHERE id=target AND tenant_id=actor.tenant_id AND role IN ('student','instructor') AND status='active') THEN RETURN jsonb_build_object('error',404); END IF;
 expiry=identity.issue_account_recovery(target,p_data->>'hash',actor.membership_id::text);
 IF expiry IS NULL THEN RETURN jsonb_build_object('error',409); END IF;
 RETURN jsonb_build_object('expires_at',expiry);
 END IF;
 SELECT * INTO inv FROM identity.student_invitations WHERE id=(p_data->>'invitation_id')::uuid AND school_id=actor.tenant_id AND target_role IN ('student','instructor');
 IF NOT FOUND THEN RETURN jsonb_build_object('error',404); END IF;
 -- Same lock order as invitation creation; activation serializes on the invitation row.
 PERFORM pg_advisory_xact_lock(hashtextextended('invite:'||actor.tenant_id::text||':'||inv.email,0));
 SELECT * INTO inv FROM identity.student_invitations WHERE id=inv.id FOR UPDATE;
 IF inv.used_at IS NOT NULL OR inv.revoked_at IS NOT NULL OR inv.version<>(p_data->>'expected_version')::integer THEN RETURN jsonb_build_object('error',409); END IF;
 IF p_action='renew' THEN
 IF EXISTS(SELECT 1 FROM identity.local_accounts WHERE email=inv.email) THEN RETURN jsonb_build_object('error',409); END IF;
 expiry=clock_timestamp()+interval '72 hours';
 UPDATE identity.student_invitations SET token_hash=p_data->>'hash',expires_at=expiry,version=version+1 WHERE id=inv.id;
 ELSIF p_action='revoke' THEN
 UPDATE identity.student_invitations SET revoked_at=clock_timestamp(),version=version+1 WHERE id=inv.id;
 ELSE RETURN jsonb_build_object('error',422); END IF;
 INSERT INTO identity.account_access_audit(tenant_id,actor,event,invitation_id) VALUES(actor.tenant_id,actor.membership_id::text,CASE WHEN p_action='renew' THEN 'invite_renewed' ELSE 'invite_revoked' END,inv.id);
 RETURN jsonb_build_object('saved',true,'email',inv.email,'expires_at',expiry);
END $$;
REVOKE ALL ON FUNCTION identity.account_support(text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.account_support(text,text,jsonb) TO sya9a_student_runtime;

CREATE FUNCTION identity.redeem_account_recovery(p_hash text,p_email text,p_password text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE rec identity.account_recovery; tenant uuid;
BEGIN
 SELECT * INTO rec FROM identity.account_recovery WHERE token_hash=p_hash;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT m.tenant_id INTO tenant FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id
 JOIN identity.local_accounts a ON a.membership_id=m.id
 WHERE m.id=rec.membership_id AND a.email=p_email AND m.status='active' AND t.status='active'
 AND m.role IN ('student','instructor','school_manager') FOR UPDATE OF m;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO rec FROM identity.account_recovery WHERE id=rec.id FOR UPDATE;
 IF rec.used_at IS NOT NULL OR rec.revoked_at IS NOT NULL OR rec.expires_at<=clock_timestamp() THEN RETURN false; END IF;
 UPDATE identity.local_accounts SET password_hash=p_password WHERE membership_id=rec.membership_id;
 DELETE FROM identity.local_sessions WHERE membership_id=rec.membership_id;
 UPDATE identity.account_recovery SET used_at=clock_timestamp() WHERE id=rec.id;
 INSERT INTO identity.account_access_audit(tenant_id,actor,event,membership_id) VALUES(tenant,'recovery-holder','password_reset',rec.membership_id);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION identity.redeem_account_recovery(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.redeem_account_recovery(text,text,text) TO sya9a_student_runtime;

-- A login verified before a concurrent reset cannot mint a new session afterwards.
CREATE FUNCTION identity.portal_new_session(p_member uuid,p_hash text,p_expected_password text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM 1 FROM identity.local_accounts WHERE membership_id=p_member AND password_hash=p_expected_password FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id WHERE m.id=p_member AND m.status='active' AND t.status='active') THEN RETURN false; END IF;
 PERFORM identity.portal_new_session(p_member,p_hash);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION identity.portal_new_session(uuid,text) FROM sya9a_student_runtime;
REVOKE ALL ON FUNCTION identity.portal_new_session(uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.portal_new_session(uuid,text,text) TO sya9a_student_runtime;

CREATE FUNCTION identity.revoke_recovery_on_suspension() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF NEW.status='inactive' AND OLD.status IS DISTINCT FROM NEW.status THEN
  UPDATE identity.account_recovery SET revoked_at=clock_timestamp() WHERE membership_id=NEW.id AND used_at IS NULL AND revoked_at IS NULL;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION identity.revoke_recovery_on_suspension() FROM PUBLIC;
CREATE TRIGGER suspend_recovery AFTER UPDATE OF status ON identity.memberships FOR EACH ROW EXECUTE FUNCTION identity.revoke_recovery_on_suspension();
