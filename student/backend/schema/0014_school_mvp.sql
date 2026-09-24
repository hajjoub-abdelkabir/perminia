ALTER TABLE identity.student_invitations ADD COLUMN target_role text NOT NULL DEFAULT 'student' CHECK(target_role IN ('student','instructor','school_manager'));
CREATE FUNCTION identity.portal_credentials(p_email text)
RETURNS TABLE(membership_id uuid,password_hash text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT a.membership_id,a.password_hash FROM identity.local_accounts a
 JOIN identity.memberships m ON m.id=a.membership_id
 JOIN identity.tenants t ON t.id=m.tenant_id
 WHERE a.email=p_email AND m.status='active' AND m.role IN ('student','instructor','school_manager') AND t.status='active'
$$;

CREATE FUNCTION identity.portal_new_session(p_member uuid,p_hash text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id WHERE m.id=p_member AND m.status='active' AND m.role IN ('student','instructor','school_manager') AND t.status='active') THEN
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

CREATE FUNCTION identity.portal_session(p_hash text)
RETURNS TABLE(membership_id uuid,tenant_id uuid,display_name text,email text,category_id text,preferred_locale text,created_at timestamptz,school_id uuid,school_name text,school_code text,role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT a.membership_id,m.tenant_id,a.display_name,a.email,p.category_id,p.preferred_locale,a.created_at,
 s.tenant_id,CASE WHEN s.tenant_id IS NOT NULL THEN t.name ELSE NULL END,s.code,m.role
 FROM identity.local_sessions x JOIN identity.local_accounts a ON a.membership_id=x.membership_id
 JOIN identity.memberships m ON m.id=a.membership_id
 JOIN identity.tenants t ON t.id=m.tenant_id
 LEFT JOIN identity.learner_profiles p ON p.membership_id=m.id AND p.tenant_id=m.tenant_id
 LEFT JOIN identity.schools s ON s.tenant_id=m.tenant_id
 WHERE x.token_hash=p_hash AND x.expires_at>now() AND m.status='active' AND m.role IN ('student','instructor','school_manager') AND t.status='active'
$$;
CREATE OR REPLACE FUNCTION identity.auth_activate(p_invite text,p_email text,p_name text,p_password text,p_session text)
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
 INSERT INTO identity.memberships(tenant_id,user_id,role) VALUES(i.school_id,u,i.target_role) RETURNING id INTO m;
 IF i.target_role='student' THEN INSERT INTO identity.learner_profiles(membership_id,tenant_id,category_id) VALUES(m,i.school_id,'B'); END IF;
 INSERT INTO identity.local_accounts(membership_id,email,display_name,password_hash) VALUES(m,p_email,p_name,p_password);
 INSERT INTO identity.local_sessions(token_hash,membership_id) VALUES(p_session,m);
 UPDATE identity.student_invitations SET used_at=clock_timestamp(),membership_id=m WHERE id=i.id;
 INSERT INTO identity.provisioning_audit(school_id,invitation_id,membership_id,event_type,actor)
 VALUES(i.school_id,i.id,m,'student_activated','student-invitation');
 RETURN m;
END $$;

REVOKE ALL ON FUNCTION identity.portal_credentials(text),identity.portal_new_session(uuid,text),identity.portal_session(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.portal_credentials(text),identity.portal_new_session(uuid,text),identity.portal_session(text) TO sya9a_student_runtime;

CREATE TABLE identity.school_student_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL,student_id uuid NOT NULL,teacher_id uuid NOT NULL,assigned_by uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),ended_at timestamptz,
 FOREIGN KEY(tenant_id,student_id) REFERENCES identity.memberships(tenant_id,id),
 FOREIGN KEY(tenant_id,teacher_id) REFERENCES identity.memberships(tenant_id,id),
 FOREIGN KEY(tenant_id,assigned_by) REFERENCES identity.memberships(tenant_id,id)
);
CREATE UNIQUE INDEX current_student_teacher ON identity.school_student_links(tenant_id,student_id) WHERE ended_at IS NULL;
CREATE INDEX teacher_students ON identity.school_student_links(tenant_id,teacher_id) WHERE ended_at IS NULL;
CREATE TABLE learning.school_tasks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL,student_id uuid NOT NULL,assigned_by uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('lesson','series')),target_id uuid NOT NULL,title text NOT NULL,
 note text NOT NULL DEFAULT '' CHECK(length(note)<=400),due_on date,
 state text NOT NULL DEFAULT 'open' CHECK(state IN ('open','done','cancelled')),
 created_at timestamptz NOT NULL DEFAULT now(),completed_at timestamptz,
 FOREIGN KEY(tenant_id,student_id) REFERENCES identity.memberships(tenant_id,id),
 FOREIGN KEY(tenant_id,assigned_by) REFERENCES identity.memberships(tenant_id,id)
);
CREATE UNIQUE INDEX one_open_assignment ON learning.school_tasks(tenant_id,student_id,kind,target_id) WHERE state='open';
CREATE INDEX student_school_tasks ON learning.school_tasks(tenant_id,student_id,created_at DESC);
-- No raw runtime table access. Entry point authenticates the live session itself.
REVOKE ALL ON identity.school_student_links,learning.school_tasks FROM PUBLIC,sya9a_student_runtime;

CREATE FUNCTION learning.school_task_ready(p_task learning.school_tasks) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT CASE WHEN p_task.kind='lesson' THEN
 EXISTS(SELECT 1 FROM content.preview_lessons WHERE revision_id=p_task.target_id)
 AND NOT EXISTS(SELECT 1 FROM content.lesson_sections s WHERE s.revision_id=p_task.target_id AND NOT EXISTS(
 SELECT 1 FROM learning.lesson_section_progress p WHERE p.tenant_id=p_task.tenant_id AND p.membership_id=p_task.student_id
 AND p.revision_id=s.revision_id AND p.section_position=s.position AND p.completed))
 ELSE EXISTS(SELECT 1 FROM learning.training_runs r WHERE r.tenant_id=p_task.tenant_id AND r.membership_id=p_task.student_id
 AND r.series_id=p_task.target_id AND r.state='completed' AND r.created_at>=p_task.created_at
 AND EXISTS(SELECT 1 FROM learning.training_items i JOIN learning.training_answers a ON a.item_id=i.id WHERE i.run_id=r.id AND a.status='answered')) END
$$;
REVOKE ALL ON FUNCTION learning.school_task_ready(learning.school_tasks) FROM PUBLIC;

CREATE FUNCTION identity.school_portal(p_session text,p_action text,p_data jsonb DEFAULT '{}') RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor record; target uuid; teacher uuid; existing uuid; task learning.school_tasks;
 result jsonb; label text; token_id uuid;
BEGIN
 SELECT * INTO actor FROM identity.portal_session(p_session);
 IF NOT FOUND OR actor.school_id IS NULL THEN RETURN jsonb_build_object('error',401); END IF;
 -- Stabilize authorization against concurrent deactivation and school suspension.
 PERFORM 1 FROM identity.memberships m JOIN identity.tenants t ON t.id=m.tenant_id
 WHERE m.id=actor.membership_id AND m.status='active' AND t.status='active' FOR SHARE OF m,t;
 IF NOT FOUND THEN RETURN jsonb_build_object('error',401); END IF;
 IF p_action='my_tasks' AND actor.role='student' THEN
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC),'[]') INTO result FROM (
 SELECT a.*,u.display_name AS teacher_name,l.slug,
 CASE WHEN a.kind='lesson' THEN l.id IS NOT NULL ELSE s.id IS NOT NULL END AS available,
 learning.school_task_ready(a) AS ready FROM learning.school_tasks a
 JOIN identity.local_accounts u ON u.membership_id=a.assigned_by
 LEFT JOIN content.preview_lessons l ON a.kind='lesson' AND l.revision_id=a.target_id
 LEFT JOIN content.preview_series s ON a.kind='series' AND s.id=a.target_id
 WHERE a.tenant_id=actor.tenant_id AND a.student_id=actor.membership_id ORDER BY a.created_at DESC LIMIT 100) x;
 RETURN jsonb_build_object('items',result);
 END IF;
 IF p_action='complete' AND actor.role='student' THEN
 SELECT * INTO task FROM learning.school_tasks WHERE id=(p_data->>'task_id')::uuid AND tenant_id=actor.tenant_id AND student_id=actor.membership_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error',404); END IF;
 IF task.state='done' THEN RETURN jsonb_build_object('saved',true); END IF;
 IF task.state<>'open' OR NOT learning.school_task_ready(task) THEN RETURN jsonb_build_object('error',409); END IF;
 UPDATE learning.school_tasks SET state='done',completed_at=now() WHERE id=task.id;
 RETURN jsonb_build_object('saved',true);
 END IF;
 IF actor.role NOT IN ('instructor','school_manager') THEN RETURN jsonb_build_object('error',403); END IF;
 IF p_action IN ('invite','link','status') AND actor.role<>'school_manager' THEN RETURN jsonb_build_object('error',403); END IF;
 IF p_action='roster' THEN
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.display_name),'[]') INTO result FROM (
 SELECT m.id,a.display_name,a.email,m.role,m.status,ln.id AS link_id,ln.teacher_id,ta.display_name AS teacher_name,
 (SELECT count(*) FROM learning.lesson_section_progress p JOIN content.preview_lessons l ON l.revision_id=p.revision_id WHERE p.tenant_id=m.tenant_id AND p.membership_id=m.id AND p.completed) AS read_sections,
 (SELECT count(*) FROM learning.training_runs r WHERE r.tenant_id=m.tenant_id AND r.membership_id=m.id AND r.state='completed' AND EXISTS(SELECT 1 FROM learning.training_items i JOIN learning.training_answers ans ON ans.item_id=i.id WHERE i.run_id=r.id AND ans.status='answered')) AS training_count,
 (SELECT count(*) FROM learning.school_tasks k WHERE k.tenant_id=m.tenant_id AND k.student_id=m.id AND k.state='open') AS open_tasks,
 (SELECT max(day) FROM learning.reading_activity r WHERE r.tenant_id=m.tenant_id AND r.membership_id=m.id AND r.origin='completion') AS last_reading_on
 FROM identity.memberships m JOIN identity.local_accounts a ON a.membership_id=m.id
 LEFT JOIN identity.school_student_links ln ON ln.tenant_id=m.tenant_id AND ln.student_id=m.id AND ln.ended_at IS NULL
 LEFT JOIN identity.local_accounts ta ON ta.membership_id=ln.teacher_id
 WHERE m.tenant_id=actor.tenant_id AND m.role IN ('student','instructor') AND
 (actor.role='school_manager' OR (m.role='student' AND ln.teacher_id=actor.membership_id))) x;
 RETURN jsonb_build_object('items',result);
 END IF;
 IF p_action='invite' AND actor.role='school_manager' THEN
 IF p_data->>'role' NOT IN ('student','instructor') OR length(p_data->>'hash')<>64 THEN RETURN jsonb_build_object('error',422); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('invite:'||actor.tenant_id::text||':'||(p_data->>'email'),0));
 IF EXISTS(SELECT 1 FROM identity.local_accounts WHERE email=p_data->>'email') THEN RETURN jsonb_build_object('error',409); END IF;
 -- Do not silently replace a pending invitation; expire old invitations before issuing another.
 IF EXISTS(SELECT 1 FROM identity.student_invitations WHERE school_id=actor.tenant_id AND email=p_data->>'email' AND used_at IS NULL AND revoked_at IS NULL AND expires_at>now()) THEN RETURN jsonb_build_object('error',409); END IF;
 UPDATE identity.student_invitations SET revoked_at=now() WHERE school_id=actor.tenant_id AND email=p_data->>'email' AND used_at IS NULL AND revoked_at IS NULL;
 INSERT INTO identity.student_invitations(school_id,email,target_role,token_hash,expires_at)
 VALUES(actor.tenant_id,p_data->>'email',p_data->>'role',p_data->>'hash',now()+interval '72 hours') RETURNING id INTO token_id;
 INSERT INTO identity.provisioning_audit(school_id,invitation_id,event_type,actor) VALUES(actor.tenant_id,token_id,'invitation_created',actor.membership_id::text);
 RETURN jsonb_build_object('saved',true,'expires_at',now()+interval '72 hours');
 END IF;
 target=(p_data->>'student_id')::uuid;
 PERFORM 1 FROM identity.memberships WHERE id=target AND tenant_id=actor.tenant_id AND role IN ('student','instructor') FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error',404); END IF;
 IF p_action='status' AND actor.role='school_manager' THEN
 IF p_data->>'status' NOT IN ('active','inactive') THEN RETURN jsonb_build_object('error',422); END IF;
 UPDATE identity.memberships SET status=p_data->>'status' WHERE id=target;
 IF p_data->>'status'='inactive' THEN DELETE FROM identity.local_sessions WHERE membership_id=target; END IF;
 RETURN jsonb_build_object('saved',true);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM identity.memberships WHERE id=target AND role='student') THEN RETURN jsonb_build_object('error',404); END IF;
 SELECT id INTO existing FROM identity.school_student_links WHERE tenant_id=actor.tenant_id AND student_id=target AND ended_at IS NULL;
 IF p_action='link' AND actor.role='school_manager' THEN
 IF existing IS DISTINCT FROM (p_data->>'expected_link_id')::uuid THEN RETURN jsonb_build_object('error',409); END IF;
 teacher=(p_data->>'teacher_id')::uuid;
 IF teacher IS NOT NULL AND NOT EXISTS(SELECT 1 FROM identity.memberships WHERE id=teacher AND tenant_id=actor.tenant_id AND role='instructor' AND status='active') THEN RETURN jsonb_build_object('error',422); END IF;
 UPDATE identity.school_student_links SET ended_at=now() WHERE id=existing;
 IF teacher IS NOT NULL THEN INSERT INTO identity.school_student_links(tenant_id,student_id,teacher_id,assigned_by) VALUES(actor.tenant_id,target,teacher,actor.membership_id); END IF;
 RETURN jsonb_build_object('saved',true);
 END IF;
 IF actor.role='instructor' AND NOT EXISTS(SELECT 1 FROM identity.school_student_links WHERE id=existing AND teacher_id=actor.membership_id) THEN RETURN jsonb_build_object('error',404); END IF;
 IF p_action='detail' THEN
 SELECT coalesce(jsonb_agg(to_jsonb(k) ORDER BY k.created_at DESC),'[]') INTO result FROM (SELECT * FROM learning.school_tasks WHERE tenant_id=actor.tenant_id AND student_id=target ORDER BY created_at DESC LIMIT 100) k;
 RETURN jsonb_build_object('tasks',result,'lessons',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.revision_id,'title',l.title_ar,'completed_sections',(SELECT count(*) FROM learning.lesson_section_progress p WHERE p.tenant_id=actor.tenant_id AND p.membership_id=target AND p.revision_id=l.revision_id AND p.completed),'section_count',l.section_count) ORDER BY l.position),'[]') FROM content.preview_lessons l));
 END IF;
 IF p_action='assign' THEN
 IF NOT EXISTS(SELECT 1 FROM identity.memberships WHERE id=target AND status='active') THEN RETURN jsonb_build_object('error',409); END IF;
 IF p_data->>'kind'='lesson' THEN SELECT title_ar INTO label FROM content.preview_lessons WHERE revision_id=(p_data->>'target_id')::uuid;
 ELSIF p_data->>'kind'='series' THEN SELECT title INTO label FROM content.preview_series WHERE id=(p_data->>'target_id')::uuid;
 ELSE RETURN jsonb_build_object('error',422); END IF;
 IF label IS NULL THEN RETURN jsonb_build_object('error',404); END IF;
 INSERT INTO learning.school_tasks(tenant_id,student_id,assigned_by,kind,target_id,title,note,due_on)
 VALUES(actor.tenant_id,target,actor.membership_id,p_data->>'kind',(p_data->>'target_id')::uuid,label,coalesce(p_data->>'note',''),(p_data->>'due_on')::date)
 ON CONFLICT(tenant_id,student_id,kind,target_id) WHERE state='open' DO NOTHING;
 RETURN jsonb_build_object('saved',true);
 END IF;
 IF p_action='cancel' THEN
 UPDATE learning.school_tasks SET state='cancelled' WHERE id=(p_data->>'task_id')::uuid AND tenant_id=actor.tenant_id AND student_id=target AND state='open';
 IF NOT FOUND THEN RETURN jsonb_build_object('error',409); END IF;
 RETURN jsonb_build_object('saved',true);
 END IF;
 RETURN jsonb_build_object('error',403);
END $$;
REVOKE ALL ON FUNCTION identity.school_portal(text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.school_portal(text,text,jsonb) TO sya9a_student_runtime;
