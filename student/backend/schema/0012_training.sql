CREATE TABLE learning.training_runs (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, membership_id uuid NOT NULL, request_id uuid NOT NULL,
 series_id uuid REFERENCES content.assessments, assessment_revision_id uuid REFERENCES content.assessment_revisions,
 mode text NOT NULL CHECK(mode IN ('preview','adaptive')), state text NOT NULL DEFAULT 'active' CHECK(state IN ('active','completed','abandoned')),
 title text NOT NULL, policy_version text NOT NULL DEFAULT 'training-v1',
 created_at timestamptz NOT NULL DEFAULT now(), closed_at timestamptz,
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id),
 UNIQUE(id,tenant_id,membership_id), UNIQUE(tenant_id,membership_id,request_id)
);
CREATE UNIQUE INDEX one_active_training ON learning.training_runs(tenant_id,membership_id) WHERE state='active';
CREATE INDEX training_history ON learning.training_runs(tenant_id,membership_id,created_at DESC);
CREATE TABLE learning.training_items (
 id uuid PRIMARY KEY, run_id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 position integer NOT NULL CHECK(position>0), revision_id uuid NOT NULL REFERENCES content.question_revisions,
 payload jsonb NOT NULL, gradable boolean NOT NULL, selection_reason text NOT NULL,
 started_at timestamptz, deadline timestamptz, draft_choices uuid[] NOT NULL DEFAULT '{}', selection_version integer NOT NULL DEFAULT 0,
 FOREIGN KEY(run_id,tenant_id,membership_id) REFERENCES learning.training_runs(id,tenant_id,membership_id),
 UNIQUE(run_id,position), UNIQUE(id,tenant_id,membership_id),CHECK(deadline IS NULL OR deadline=started_at+interval '30 seconds')
);
CREATE TABLE learning.training_answers (
 item_id uuid PRIMARY KEY, tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 status text NOT NULL CHECK(status IN ('answered','skipped','expired')),
 choices uuid[] NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 outcome text CHECK(outcome IN ('correct','wrong','unanswered','disputed')),
 evaluator_version text NOT NULL DEFAULT 'exact-set-v1',
 FOREIGN KEY(item_id,tenant_id,membership_id) REFERENCES learning.training_items(id,tenant_id,membership_id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['training_runs','training_items','training_answers'] LOOP
  EXECUTE 'ALTER TABLE learning.'||t||' ENABLE ROW LEVEL SECURITY';
  EXECUTE 'ALTER TABLE learning.'||t||' FORCE ROW LEVEL SECURITY';
  EXECUTE 'CREATE POLICY learner_scope ON learning.'||t||' USING(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id=nullif(current_setting(''app.membership_id'',true),'''')::uuid) WITH CHECK(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id=nullif(current_setting(''app.membership_id'',true),'''')::uuid)';
 END LOOP;
END $$;
GRANT SELECT,INSERT ON learning.training_runs,learning.training_items TO sya9a_student_runtime;
GRANT UPDATE(state,closed_at) ON learning.training_runs TO sya9a_student_runtime;
GRANT UPDATE(started_at,deadline,draft_choices,selection_version) ON learning.training_items TO sya9a_student_runtime;
GRANT SELECT ON learning.training_answers TO sya9a_student_runtime;
GRANT INSERT(item_id,tenant_id,membership_id,status,choices) ON learning.training_answers TO sya9a_student_runtime;
CREATE FUNCTION learning.freeze_training_item() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF (to_jsonb(NEW)-ARRAY['started_at','deadline','draft_choices','selection_version']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['started_at','deadline','draft_choices','selection_version']) THEN RAISE EXCEPTION 'Frozen question snapshot'; END IF;
 IF OLD.started_at IS NOT NULL AND (NEW.started_at,NEW.deadline) IS DISTINCT FROM (OLD.started_at,OLD.deadline) THEN RAISE EXCEPTION 'Deadline cannot change'; END IF;
 IF EXISTS(SELECT 1 FROM learning.training_answers WHERE item_id=OLD.id) THEN RAISE EXCEPTION 'Answer finalized'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER frozen_training BEFORE UPDATE ON learning.training_items FOR EACH ROW EXECUTE FUNCTION learning.freeze_training_item();
REVOKE ALL ON FUNCTION learning.freeze_training_item() FROM PUBLIC;

-- Content projections never include the answer key or explanation before submission.
CREATE VIEW content.training_pool AS
 SELECT q.*,r.status,r.content_hash,coalesce(c.duplicate_family_id,c.id) AS family_id,
 coalesce((SELECT jsonb_agg(jsonb_build_object('id',k.id,'label',k.label)) FROM content.question_concepts qc JOIN content.concepts k ON k.id=qc.concept_id WHERE qc.revision_id=r.id AND qc.approval_status='approved'),'[]'::jsonb) AS concepts
 FROM content.preview_questions q JOIN content.question_revisions r ON r.id=q.revision_id JOIN content.questions c ON c.id=r.question_id;
GRANT SELECT ON content.training_pool TO sya9a_student_runtime;

-- The only grading entry point accepts a persisted answer ID, never arbitrary guessed choices.
CREATE FUNCTION learning.evaluate_training_answer(p_item uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE rec record; revision_state text;
BEGIN
 SELECT a.*,i.revision_id,i.gradable INTO rec FROM learning.training_answers a JOIN learning.training_items i ON i.id=a.item_id
 WHERE a.item_id=p_item AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND a.membership_id=nullif(current_setting('app.membership_id',true),'')::uuid FOR UPDATE OF a;
 IF NOT FOUND OR NOT rec.gradable OR rec.outcome IS NOT NULL THEN RETURN; END IF;
 SELECT status INTO revision_state FROM content.question_revisions WHERE id=rec.revision_id FOR SHARE;
 UPDATE learning.training_answers SET outcome=CASE WHEN revision_state<>'published' THEN 'disputed'
  WHEN rec.status<>'answered' THEN 'unanswered'
  WHEN content.exact_set_score(rec.revision_id,rec.choices) THEN 'correct' ELSE 'wrong' END WHERE item_id=p_item;
END $$;
REVOKE ALL ON FUNCTION learning.evaluate_training_answer(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION learning.evaluate_training_answer(uuid) TO sya9a_student_runtime;

CREATE FUNCTION learning.training_feedback(p_run uuid) RETURNS TABLE(item_id uuid,explanation text,correct_choices uuid[]) LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT i.id,l.explanation,ARRAY(SELECT k.choice_id FROM content.answer_keys k WHERE k.revision_id=i.revision_id ORDER BY k.choice_id)
 FROM learning.training_runs r JOIN learning.training_items i ON i.run_id=r.id
 JOIN content.question_revisions q ON q.id=i.revision_id JOIN content.question_localizations l ON l.revision_id=q.id AND l.locale='ary-MA'
 WHERE r.id=p_run AND r.state='completed' AND i.gradable AND q.status='published'
 AND r.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND r.membership_id=nullif(current_setting('app.membership_id',true),'')::uuid;
$$;
REVOKE ALL ON FUNCTION learning.training_feedback(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION learning.training_feedback(uuid) TO sya9a_student_runtime;

CREATE VIEW learning.training_evidence WITH(security_invoker=true) AS
 SELECT a.*,i.revision_id,i.run_id,r.mode FROM learning.training_answers a JOIN learning.training_items i ON i.id=a.item_id
 JOIN learning.training_runs r ON r.id=i.run_id WHERE i.gradable AND r.state='completed' AND a.outcome IN ('correct','wrong','unanswered');
GRANT SELECT ON learning.training_evidence TO sya9a_student_runtime;
