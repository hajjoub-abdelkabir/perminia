CREATE SCHEMA content;
CREATE SCHEMA ingestion;
CREATE SCHEMA identity;
CREATE SCHEMA learning;
CREATE SCHEMA intelligence;

CREATE TABLE identity.tenants (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE identity.users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), auth_subject text UNIQUE NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE identity.memberships (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES identity.tenants, user_id uuid NOT NULL REFERENCES identity.users, role text NOT NULL CHECK(role IN ('student','reviewer','instructor','admin')), status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')), UNIQUE(tenant_id,user_id), UNIQUE(tenant_id,id));
CREATE TABLE content.permit_categories (id text PRIMARY KEY, label text NOT NULL);
INSERT INTO content.permit_categories VALUES ('B','Permis B');
CREATE TABLE identity.learner_profiles (membership_id uuid PRIMARY KEY REFERENCES identity.memberships, tenant_id uuid NOT NULL, category_id text NOT NULL REFERENCES content.permit_categories, preferred_locale text NOT NULL DEFAULT 'ary-MA', FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));
CREATE TABLE ingestion.content_sources (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL UNIQUE, base_url text NOT NULL, publisher_type text NOT NULL DEFAULT 'unverified', rights_status text NOT NULL DEFAULT 'unknown' CHECK(rights_status IN ('unknown','permitted','restricted')), rights_evidence_ref text, checked_at timestamptz);
CREATE TABLE ingestion.import_batches (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id uuid NOT NULL REFERENCES ingestion.content_sources, input_sha256 text NOT NULL, importer_version text NOT NULL, enrichment_script_sha256 text NOT NULL, archive_key text NOT NULL, status text NOT NULL CHECK(status IN ('pending','complete','failed')), started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz, report jsonb NOT NULL DEFAULT '{}', UNIQUE(source_id,input_sha256,importer_version));
CREATE TABLE ingestion.source_records (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), batch_id uuid NOT NULL REFERENCES ingestion.import_batches, source_key text NOT NULL, source_series_key text NOT NULL, source_position integer NOT NULL CHECK(source_position>0), source_url text NOT NULL, raw_payload jsonb NOT NULL, raw_sha256 text NOT NULL, scraped_at timestamptz, UNIQUE(batch_id,source_key));
CREATE TABLE ingestion.enrichment_candidates (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_record_id uuid NOT NULL REFERENCES ingestion.source_records, field_name text NOT NULL, value jsonb NOT NULL, producer_kind text NOT NULL CHECK(producer_kind IN ('rule_based','model','source_derived')), producer_version text NOT NULL, review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','approved','rejected')), UNIQUE(source_record_id,field_name));
CREATE TABLE content.duplicate_families (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), note text NOT NULL);
CREATE TABLE content.questions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id uuid NOT NULL REFERENCES ingestion.content_sources, source_key text NOT NULL, country_code text NOT NULL DEFAULT 'MA', category_id text NOT NULL REFERENCES content.permit_categories, duplicate_family_id uuid REFERENCES content.duplicate_families, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_id,source_key));
CREATE TABLE ingestion.question_sources (question_id uuid NOT NULL REFERENCES content.questions, source_record_id uuid NOT NULL REFERENCES ingestion.source_records, PRIMARY KEY(question_id,source_record_id));
CREATE TABLE content.question_revisions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), question_id uuid NOT NULL REFERENCES content.questions, revision_number integer NOT NULL CHECK(revision_number>0), status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','retired','revoked')), response_type text NOT NULL CHECK(response_type IN ('single','multiple','grouped')), grading_policy_version text NOT NULL DEFAULT 'exact-set-v1', content_hash text NOT NULL, source_record_id uuid NOT NULL REFERENCES ingestion.source_records, needs_prompt_reconstruction boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz, UNIQUE(question_id,revision_number), UNIQUE(id,question_id));
CREATE INDEX revision_status_idx ON content.question_revisions(status,question_id);
CREATE TABLE content.question_localizations (revision_id uuid NOT NULL REFERENCES content.question_revisions, locale text NOT NULL, prompt text NOT NULL, explanation text NOT NULL, PRIMARY KEY(revision_id,locale));
CREATE TABLE content.choice_groups (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), revision_id uuid NOT NULL REFERENCES content.question_revisions, position integer NOT NULL CHECK(position>0), selection_min integer CHECK(selection_min>=0), selection_max integer, rule_reviewed boolean NOT NULL DEFAULT false, CHECK(selection_max>=selection_min), UNIQUE(revision_id,position), UNIQUE(id,revision_id));
CREATE TABLE content.choice_group_localizations (group_id uuid NOT NULL REFERENCES content.choice_groups, locale text NOT NULL, label text, PRIMARY KEY(group_id,locale));
CREATE TABLE content.choices (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), revision_id uuid NOT NULL REFERENCES content.question_revisions, group_id uuid NOT NULL, source_choice_number integer NOT NULL CHECK(source_choice_number>0), display_position integer NOT NULL CHECK(display_position>0), FOREIGN KEY(group_id,revision_id) REFERENCES content.choice_groups(id,revision_id), UNIQUE(revision_id,source_choice_number), UNIQUE(revision_id,display_position), UNIQUE(id,revision_id));
CREATE TABLE content.choice_localizations (choice_id uuid NOT NULL REFERENCES content.choices, locale text NOT NULL, text text NOT NULL CHECK(length(trim(text))>0), PRIMARY KEY(choice_id,locale));
CREATE TABLE content.answer_keys (revision_id uuid NOT NULL REFERENCES content.question_revisions, choice_id uuid NOT NULL, PRIMARY KEY(revision_id,choice_id), FOREIGN KEY(choice_id,revision_id) REFERENCES content.choices(id,revision_id));
CREATE TABLE content.media_assets (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id uuid NOT NULL REFERENCES ingestion.content_sources, sha256 text UNIQUE, object_key text UNIQUE, original_url text NOT NULL, mime text NOT NULL, byte_size bigint CHECK(byte_size>0), availability text NOT NULL CHECK(availability IN ('local','remote_only','unavailable')), CHECK((availability='local' AND sha256 IS NOT NULL AND object_key IS NOT NULL AND byte_size IS NOT NULL) OR availability<>'local'), UNIQUE(source_id,original_url));
CREATE TABLE content.question_media (revision_id uuid NOT NULL REFERENCES content.question_revisions, asset_id uuid NOT NULL REFERENCES content.media_assets, role text NOT NULL CHECK(role IN ('original_card','alternate','audio','scene','correction')), locale text NOT NULL, position integer NOT NULL CHECK(position>0), reveal_stage text NOT NULL DEFAULT 'withheld' CHECK(reveal_stage IN ('withheld','question','feedback')), embedded_choice_numbers boolean NOT NULL DEFAULT true, alt_text text, PRIMARY KEY(revision_id,role,position));
CREATE TABLE content.topics (id text PRIMARY KEY, label text NOT NULL);
CREATE TABLE content.question_topics (revision_id uuid NOT NULL REFERENCES content.question_revisions, topic_id text NOT NULL REFERENCES content.topics, PRIMARY KEY(revision_id,topic_id));
CREATE TABLE content.concepts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), topic_id text NOT NULL REFERENCES content.topics, code text UNIQUE NOT NULL, label text NOT NULL);
CREATE TABLE content.question_concepts (revision_id uuid NOT NULL REFERENCES content.question_revisions, concept_id uuid NOT NULL REFERENCES content.concepts, weight numeric NOT NULL CHECK(weight>0 AND weight<=1), approval_status text NOT NULL DEFAULT 'pending' CHECK(approval_status IN ('pending','approved','rejected')), PRIMARY KEY(revision_id,concept_id));
CREATE TABLE content.misconceptions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), concept_id uuid NOT NULL REFERENCES content.concepts, description text NOT NULL);
CREATE TABLE content.choice_misconceptions (choice_id uuid NOT NULL REFERENCES content.choices, misconception_id uuid NOT NULL REFERENCES content.misconceptions, PRIMARY KEY(choice_id,misconception_id));
CREATE TABLE content.knowledge_documents (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id uuid NOT NULL REFERENCES ingestion.content_sources, title text NOT NULL, version text NOT NULL, jurisdiction text NOT NULL DEFAULT 'MA', review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','approved','revoked')), effective_from date, effective_to date, CHECK(effective_to IS NULL OR effective_to>=effective_from));
CREATE TABLE content.knowledge_chunks (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), document_id uuid NOT NULL REFERENCES content.knowledge_documents, section_ref text NOT NULL, text text NOT NULL, sha256 text NOT NULL, UNIQUE(document_id,section_ref));
CREATE TABLE content.question_citations (revision_id uuid NOT NULL REFERENCES content.question_revisions, chunk_id uuid NOT NULL REFERENCES content.knowledge_chunks, supported_claim text NOT NULL, validation_status text NOT NULL DEFAULT 'pending' CHECK(validation_status IN ('pending','approved','rejected')), PRIMARY KEY(revision_id,chunk_id));
CREATE TABLE content.content_reviews (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), revision_id uuid NOT NULL REFERENCES content.question_revisions, reviewer_id uuid NOT NULL REFERENCES identity.memberships, aspect text NOT NULL CHECK(aspect IN ('prompt','answer_key','explanation','media','groups','rights')), decision text NOT NULL CHECK(decision IN ('approved','rejected')), content_hash text NOT NULL, reason text NOT NULL, superseded boolean NOT NULL DEFAULT false, reviewed_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX review_revision_idx ON content.content_reviews(revision_id,aspect,reviewed_at DESC);
CREATE TABLE content.assessments (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id uuid REFERENCES ingestion.content_sources, source_key text, kind text NOT NULL CHECK(kind IN ('source_series','practice','mock')), title text NOT NULL, UNIQUE(source_id,source_key));
CREATE TABLE content.assessment_revisions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assessment_id uuid NOT NULL REFERENCES content.assessments, revision_number integer NOT NULL CHECK(revision_number>0), status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','retired')), item_count integer NOT NULL CHECK(item_count>0), time_limit_seconds integer CHECK(time_limit_seconds>0), pass_rule jsonb, scoring_policy_version text NOT NULL DEFAULT 'exact-set-v1', constraints jsonb NOT NULL DEFAULT '{}', generation_policy_version text, seed text, pool_manifest_hash text NOT NULL, UNIQUE(assessment_id,revision_number));
CREATE TABLE content.assessment_items (assessment_revision_id uuid NOT NULL REFERENCES content.assessment_revisions, position integer NOT NULL CHECK(position>0), question_revision_id uuid NOT NULL, question_id uuid NOT NULL, PRIMARY KEY(assessment_revision_id,position), UNIQUE(assessment_revision_id,question_id), FOREIGN KEY(question_revision_id,question_id) REFERENCES content.question_revisions(id,question_id));
CREATE INDEX assessment_question_idx ON content.assessment_items(question_revision_id);

CREATE TABLE learning.attempts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, assessment_revision_id uuid REFERENCES content.assessment_revisions, mode text NOT NULL CHECK(mode IN ('practice','mock')), state text NOT NULL DEFAULT 'created' CHECK(state IN ('created','in_progress','submitted','expired','abandoned')), locale text NOT NULL DEFAULT 'ary-MA', started_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz, submitted_at timestamptz, grading_policy_version text NOT NULL DEFAULT 'exact-set-v1', integrity_state text NOT NULL DEFAULT 'online' CHECK(integrity_state IN ('online','offline_unverified')), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id), UNIQUE(id,tenant_id,membership_id));
CREATE INDEX attempts_learner_idx ON learning.attempts(tenant_id,membership_id,started_at DESC);
CREATE TABLE learning.attempt_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, attempt_id uuid NOT NULL, position integer NOT NULL CHECK(position>0), question_revision_id uuid NOT NULL REFERENCES content.question_revisions, locale text NOT NULL, media_manifest jsonb NOT NULL, displayed_choice_order uuid[] NOT NULL, generation_reason text, FOREIGN KEY(attempt_id,tenant_id,membership_id) REFERENCES learning.attempts(id,tenant_id,membership_id), UNIQUE(attempt_id,position), UNIQUE(id,question_revision_id,tenant_id,membership_id));
CREATE TABLE learning.responses (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, attempt_item_id uuid NOT NULL, question_revision_id uuid NOT NULL, response_revision integer NOT NULL CHECK(response_revision>0), idempotency_key uuid NOT NULL, client_answered_at timestamptz, server_received_at timestamptz NOT NULL DEFAULT now(), duration_ms bigint CHECK(duration_ms>=0), hint_usage integer NOT NULL DEFAULT 0 CHECK(hint_usage>=0), FOREIGN KEY(attempt_item_id,question_revision_id,tenant_id,membership_id) REFERENCES learning.attempt_items(id,question_revision_id,tenant_id,membership_id), UNIQUE(attempt_item_id,response_revision), UNIQUE(tenant_id,membership_id,idempotency_key), UNIQUE(id,question_revision_id,tenant_id,membership_id));
CREATE TABLE learning.response_choices (response_id uuid NOT NULL, question_revision_id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL, choice_id uuid NOT NULL, PRIMARY KEY(response_id,choice_id), FOREIGN KEY(response_id,question_revision_id,tenant_id,membership_id) REFERENCES learning.responses(id,question_revision_id,tenant_id,membership_id), FOREIGN KEY(choice_id,question_revision_id) REFERENCES content.choices(id,revision_id));
CREATE TABLE learning.response_evaluations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), response_id uuid NOT NULL, question_revision_id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL, evaluator_version text NOT NULL, outcome text NOT NULL CHECK(outcome IN ('correct','wrong','unanswered','disputed')), score numeric NOT NULL CHECK(score>=0), max_score numeric NOT NULL CHECK(max_score>0), evaluated_at timestamptz NOT NULL DEFAULT now(), CHECK(score<=max_score), FOREIGN KEY(response_id,question_revision_id,tenant_id,membership_id) REFERENCES learning.responses(id,question_revision_id,tenant_id,membership_id), UNIQUE(response_id,evaluator_version));
CREATE TABLE learning.learning_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, event_type text NOT NULL, occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(), schema_version integer NOT NULL DEFAULT 1, payload jsonb NOT NULL, dedupe_key uuid NOT NULL, FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id), UNIQUE(tenant_id,membership_id,dedupe_key));
CREATE INDEX learning_events_learner_idx ON learning.learning_events(tenant_id,membership_id,occurred_at);
CREATE TABLE learning.bookmarks (tenant_id uuid NOT NULL, membership_id uuid NOT NULL, question_id uuid NOT NULL REFERENCES content.questions, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,membership_id,question_id), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));
CREATE TABLE learning.content_reports (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, revision_id uuid NOT NULL REFERENCES content.question_revisions, reason text NOT NULL, status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')), created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));
CREATE TABLE intelligence.mastery_snapshots (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, concept_id uuid NOT NULL REFERENCES content.concepts, algorithm_version text NOT NULL, evidence_count integer NOT NULL CHECK(evidence_count>=0), distinct_question_count integer NOT NULL CHECK(distinct_question_count>=0), mastery numeric CHECK(mastery BETWEEN 0 AND 1), confidence numeric CHECK(confidence BETWEEN 0 AND 1), evidence_cursor uuid REFERENCES learning.learning_events, created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));
CREATE TABLE intelligence.readiness_snapshots (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, algorithm_version text NOT NULL, state text NOT NULL CHECK(state IN ('insufficient_evidence','estimated')), components jsonb NOT NULL, evidence_count integer NOT NULL CHECK(evidence_count>=0), created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));
CREATE TABLE intelligence.review_schedule (tenant_id uuid NOT NULL, membership_id uuid NOT NULL, concept_id uuid NOT NULL REFERENCES content.concepts, due_at timestamptz NOT NULL, policy_version text NOT NULL, evidence jsonb NOT NULL, PRIMARY KEY(tenant_id,membership_id,concept_id), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));
CREATE INDEX review_due_idx ON intelligence.review_schedule(tenant_id,membership_id,due_at);
CREATE TABLE intelligence.generation_runs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, policy_version text NOT NULL, pool_manifest_hash text NOT NULL, constraints jsonb NOT NULL, outcome text NOT NULL CHECK(outcome IN ('selected','infeasible')), result_assessment_revision_id uuid REFERENCES content.assessment_revisions, reason text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));
CREATE TABLE intelligence.ai_runs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, task_type text NOT NULL, status text NOT NULL CHECK(status IN ('pending','running','complete','failed')), model text NOT NULL, prompt_version text NOT NULL, input_refs jsonb NOT NULL, input_hash text NOT NULL, input_tokens bigint CHECK(input_tokens>=0), output_tokens bigint CHECK(output_tokens>=0), cost numeric CHECK(cost>=0), currency text NOT NULL, pricing_snapshot jsonb NOT NULL, retry_parent uuid REFERENCES intelligence.ai_runs, created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id));

-- Private server-side grading: never include this set in pre-answer projections.
CREATE FUNCTION content.exact_set_score(p_revision uuid, p_choices uuid[]) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM content.answer_keys WHERE revision_id=p_revision)
 AND NOT EXISTS(SELECT 1 FROM unnest(p_choices) v WHERE v IS NULL)
 AND (SELECT count(*) FROM unnest(p_choices))=(SELECT count(DISTINCT v) FROM unnest(p_choices) v)
 AND ARRAY(SELECT choice_id FROM content.answer_keys WHERE revision_id=p_revision ORDER BY choice_id)=ARRAY(SELECT v FROM unnest(p_choices) v ORDER BY v)
$$;

-- All content children use the owning revision lock, serializing publication/edit races.
CREATE FUNCTION content.guard_revision_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid; s text; parent_id uuid;
BEGIN
 IF TG_OP='DELETE' THEN rid=(to_jsonb(OLD)->>'revision_id')::uuid; ELSE rid=(to_jsonb(NEW)->>'revision_id')::uuid; END IF;
 IF TG_TABLE_NAME='choice_localizations' OR TG_TABLE_NAME='choice_misconceptions' THEN
   IF TG_OP='DELETE' THEN parent_id=OLD.choice_id; ELSE parent_id=NEW.choice_id; END IF;
   SELECT revision_id INTO rid FROM content.choices WHERE id=parent_id;
 ELSIF TG_TABLE_NAME='choice_group_localizations' THEN
   IF TG_OP='DELETE' THEN parent_id=OLD.group_id; ELSE parent_id=NEW.group_id; END IF;
   SELECT revision_id INTO rid FROM content.choice_groups WHERE id=parent_id;
 END IF;
 SELECT status INTO s FROM content.question_revisions WHERE id=rid FOR UPDATE;
 IF s<>'draft' THEN RAISE EXCEPTION 'Published revision content is immutable'; END IF;
 IF TG_OP='UPDATE' THEN
   IF (to_jsonb(NEW)-ARRAY['text','prompt','explanation','label','selection_min','selection_max','rule_reviewed','reveal_stage','alt_text','weight','approval_status']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['text','prompt','explanation','label','selection_min','selection_max','rule_reviewed','reveal_stage','alt_text','weight','approval_status']) THEN RAISE EXCEPTION 'Identity/order changes require delete and insert on a draft'; END IF;
 END IF;
 -- Any edit invalidates prior approvals, even if the importer hash is unchanged.
 UPDATE content.content_reviews SET superseded=true WHERE revision_id=rid AND NOT superseded;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['question_localizations','choice_groups','choice_group_localizations','choices','choice_localizations','answer_keys','question_media','question_topics','question_concepts','choice_misconceptions','question_citations'] LOOP
 EXECUTE format('CREATE TRIGGER guard_content BEFORE INSERT OR UPDATE OR DELETE ON content.%I FOR EACH ROW EXECUTE FUNCTION content.guard_revision_child()',t);
END LOOP; END $$;

CREATE FUNCTION content.guard_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN IF OLD.status<>'draft' THEN RAISE EXCEPTION 'Cannot delete a published revision'; END IF; RETURN OLD; END IF;
 IF OLD.status<>'draft' AND (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN RAISE EXCEPTION 'Published revision is immutable'; END IF;
 IF OLD.status<>'draft' AND NEW.status='draft' THEN RAISE EXCEPTION 'Cannot reopen a published revision'; END IF;
 IF NEW.status='published' AND OLD.status<>'published' THEN
   IF OLD.status<>'draft' THEN RAISE EXCEPTION 'Publish a new revision instead'; END IF;
   IF NOT EXISTS(SELECT 1 FROM content.question_localizations WHERE revision_id=NEW.id AND length(trim(prompt))>0) THEN RAISE EXCEPTION 'Reviewed prompt required'; END IF;
   IF (SELECT count(*) FROM content.choices WHERE revision_id=NEW.id)<2 OR NOT EXISTS(SELECT 1 FROM content.answer_keys WHERE revision_id=NEW.id) THEN RAISE EXCEPTION 'Valid answer set required'; END IF;
   IF EXISTS(SELECT 1 FROM content.choice_groups g WHERE g.revision_id=NEW.id AND (NOT rule_reviewed OR selection_min IS NULL OR selection_max IS NULL OR selection_max>(SELECT count(*) FROM content.choices c WHERE c.group_id=g.id) OR (SELECT count(*) FROM content.answer_keys a JOIN content.choices c ON c.id=a.choice_id WHERE c.group_id=g.id) NOT BETWEEN selection_min AND selection_max)) THEN RAISE EXCEPTION 'Reviewed group selection bounds required'; END IF;
   IF EXISTS(SELECT 1 FROM unnest(ARRAY['prompt','answer_key','explanation','media','groups','rights']) a WHERE NOT EXISTS(SELECT 1 FROM content.content_reviews r JOIN identity.memberships m ON m.id=r.reviewer_id WHERE r.revision_id=NEW.id AND r.aspect=a AND r.decision='approved' AND NOT r.superseded AND r.content_hash=NEW.content_hash AND m.role IN ('reviewer','admin') AND m.status='active')) THEN RAISE EXCEPTION 'All review aspects must be approved'; END IF;
   IF EXISTS(SELECT 1 FROM content.content_reviews WHERE revision_id=NEW.id AND NOT superseded AND decision='rejected') THEN RAISE EXCEPTION 'Unresolved rejection'; END IF;
   NEW.published_at=now();
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_publication BEFORE UPDATE OR DELETE ON content.question_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_publication();
CREATE FUNCTION ingestion.immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Source evidence is immutable'; END $$;
CREATE TRIGGER raw_immutable BEFORE UPDATE OR DELETE ON ingestion.source_records FOR EACH ROW EXECUTE FUNCTION ingestion.immutable_record();

CREATE VIEW content.published_question_prompts AS SELECT r.id AS revision_id,r.question_id,l.locale,l.prompt,r.response_type FROM content.question_revisions r JOIN content.question_localizations l ON l.revision_id=r.id WHERE r.status='published';
CREATE VIEW content.published_choices AS SELECT c.id,c.revision_id,c.group_id,c.source_choice_number,c.display_position,l.locale,l.text FROM content.choices c JOIN content.choice_localizations l ON l.choice_id=c.id JOIN content.question_revisions r ON r.id=c.revision_id WHERE r.status='published';

-- Dedicated runtime role. Password provisioned separately, never in migrations.
DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='sya9a_student_runtime') THEN CREATE ROLE sya9a_student_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END $$;
REVOKE ALL ON SCHEMA content,ingestion,identity,learning,intelligence FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA content,ingestion FROM PUBLIC;
GRANT USAGE ON SCHEMA content,learning,identity,intelligence TO sya9a_student_runtime;
GRANT SELECT ON public.app_bootstrap TO sya9a_student_runtime;
GRANT SELECT ON content.published_question_prompts,content.published_choices TO sya9a_student_runtime;
DO $$ DECLARE s text; t record; BEGIN
 FOREACH s IN ARRAY ARRAY['learning','intelligence'] LOOP
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname=s LOOP
   EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',s,t.tablename);
   EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',s,t.tablename);
   EXECUTE format('CREATE POLICY learner_scope ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id = nullif(current_setting(''app.membership_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id = nullif(current_setting(''app.membership_id'',true),'''')::uuid)',s,t.tablename);
   EXECUTE format('GRANT SELECT ON %I.%I TO sya9a_student_runtime',s,t.tablename);
  END LOOP;
 END LOOP;
END $$;
-- No public API mutations until authenticated, scoped student services are implemented.

CREATE FUNCTION content.require_draft_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.status<>'draft' THEN RAISE EXCEPTION 'Insert a draft, then publish through review'; END IF; RETURN NEW; END $$;
CREATE TRIGGER draft_revision BEFORE INSERT ON content.question_revisions FOR EACH ROW EXECUTE FUNCTION content.require_draft_insert();
CREATE TRIGGER draft_assessment BEFORE INSERT ON content.assessment_revisions FOR EACH ROW EXECUTE FUNCTION content.require_draft_insert();
CREATE FUNCTION content.guard_assessment() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' THEN IF OLD.status<>'draft' THEN RAISE EXCEPTION 'Cannot delete published assessment'; END IF; RETURN OLD; END IF;
 IF OLD.status<>'draft' AND ((to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') OR NEW.status='draft') THEN RAISE EXCEPTION 'Assessment is immutable'; END IF;
 IF NEW.status='published' AND OLD.status='draft' THEN
  IF (SELECT count(*) FROM content.assessment_items WHERE assessment_revision_id=NEW.id)<>NEW.item_count OR EXISTS(SELECT 1 FROM content.assessment_items i JOIN content.question_revisions r ON r.id=i.question_revision_id WHERE i.assessment_revision_id=NEW.id AND r.status<>'published') THEN RAISE EXCEPTION 'Assessment requires all approved items'; END IF;
 END IF;
 RETURN NEW; END $$;
CREATE TRIGGER assessment_publication BEFORE UPDATE OR DELETE ON content.assessment_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_assessment();
CREATE FUNCTION content.guard_assessment_item() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE aid uuid; s text; BEGIN
 IF TG_OP='DELETE' THEN aid=OLD.assessment_revision_id; ELSE aid=NEW.assessment_revision_id; END IF;
 IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Replace draft items using delete and insert'; END IF;
 SELECT status INTO s FROM content.assessment_revisions WHERE id=aid FOR UPDATE;
 IF s<>'draft' THEN RAISE EXCEPTION 'Assessment items are immutable'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END $$;
CREATE TRIGGER assessment_items_immutable BEFORE INSERT OR UPDATE OR DELETE ON content.assessment_items FOR EACH ROW EXECUTE FUNCTION content.guard_assessment_item();
CREATE FUNCTION learning.guard_attempt_item() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE s text; BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Presented items are immutable'; END IF;
 SELECT state INTO s FROM learning.attempts WHERE id=NEW.attempt_id FOR UPDATE;
 IF s NOT IN ('created','in_progress') THEN RAISE EXCEPTION 'Attempt is closed'; END IF;
 IF NOT EXISTS(SELECT 1 FROM content.question_revisions WHERE id=NEW.question_revision_id AND status='published') THEN RAISE EXCEPTION 'Question must be published'; END IF;
 IF ARRAY(SELECT id FROM content.choices WHERE revision_id=NEW.question_revision_id ORDER BY id) IS DISTINCT FROM ARRAY(SELECT v FROM unnest(NEW.displayed_choice_order) v ORDER BY v) THEN RAISE EXCEPTION 'Displayed choices must match revision'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER attempt_items_guard BEFORE INSERT OR UPDATE OR DELETE ON learning.attempt_items FOR EACH ROW EXECUTE FUNCTION learning.guard_attempt_item();
CREATE FUNCTION learning.guard_response() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE s text; BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Response history is immutable'; END IF;
 SELECT a.state INTO s FROM learning.attempts a JOIN learning.attempt_items i ON i.attempt_id=a.id WHERE i.id=NEW.attempt_item_id FOR UPDATE OF a;
 IF s<>'in_progress' THEN RAISE EXCEPTION 'Attempt is not in progress'; END IF; RETURN NEW; END $$;
CREATE TRIGGER responses_guard BEFORE INSERT OR UPDATE OR DELETE ON learning.responses FOR EACH ROW EXECUTE FUNCTION learning.guard_response();
CREATE FUNCTION learning.guard_response_choice() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE s text; BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Submitted choice evidence is immutable'; END IF;
 SELECT a.state INTO s FROM learning.attempts a JOIN learning.attempt_items i ON i.attempt_id=a.id JOIN learning.responses r ON r.attempt_item_id=i.id WHERE r.id=NEW.response_id FOR UPDATE OF a;
 IF s<>'in_progress' OR EXISTS(SELECT 1 FROM learning.response_evaluations WHERE response_id=NEW.response_id) THEN RAISE EXCEPTION 'Response is finalized'; END IF; RETURN NEW; END $$;
CREATE TRIGGER response_choices_guard BEFORE INSERT OR UPDATE OR DELETE ON learning.response_choices FOR EACH ROW EXECUTE FUNCTION learning.guard_response_choice();
CREATE TRIGGER evaluations_immutable BEFORE UPDATE OR DELETE ON learning.response_evaluations FOR EACH ROW EXECUTE FUNCTION ingestion.immutable_record();
CREATE TRIGGER events_immutable BEFORE UPDATE OR DELETE ON learning.learning_events FOR EACH ROW EXECUTE FUNCTION ingestion.immutable_record();
CREATE FUNCTION learning.guard_attempt_state() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Use dedicated retention procedures for learner history'; END IF;
 IF (NEW.id,NEW.tenant_id,NEW.membership_id,NEW.assessment_revision_id,NEW.mode,NEW.locale,NEW.started_at,NEW.expires_at,NEW.grading_policy_version,NEW.integrity_state) IS DISTINCT FROM (OLD.id,OLD.tenant_id,OLD.membership_id,OLD.assessment_revision_id,OLD.mode,OLD.locale,OLD.started_at,OLD.expires_at,OLD.grading_policy_version,OLD.integrity_state) THEN RAISE EXCEPTION 'Attempt identity/configuration is immutable'; END IF;
 IF OLD.state IN ('submitted','expired','abandoned') THEN RAISE EXCEPTION 'Attempt is closed'; END IF;
 IF NEW.state IS DISTINCT FROM OLD.state AND NOT ((OLD.state='created' AND NEW.state IN ('in_progress','abandoned')) OR (OLD.state='in_progress' AND NEW.state IN ('submitted','expired','abandoned'))) THEN RAISE EXCEPTION 'Invalid attempt transition'; END IF;
 IF NEW.state='submitted' THEN NEW.submitted_at=now(); END IF;
 RETURN NEW; END $$;
CREATE TRIGGER attempt_state_guard BEFORE UPDATE OR DELETE ON learning.attempts FOR EACH ROW EXECUTE FUNCTION learning.guard_attempt_state();
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA content,learning,ingestion FROM PUBLIC;

-- Publishing also requires a traceable source permission and usable reviewed media.
CREATE FUNCTION content.guard_publish_media() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.status='published' AND OLD.status='draft' THEN
  IF NOT EXISTS(SELECT 1 FROM content.questions q JOIN ingestion.content_sources s ON s.id=q.source_id WHERE q.id=NEW.question_id AND s.rights_status='permitted' AND s.rights_evidence_ref IS NOT NULL) THEN RAISE EXCEPTION 'Source permission evidence required'; END IF;
  IF NOT EXISTS(SELECT 1 FROM content.question_media m JOIN content.media_assets a ON a.id=m.asset_id WHERE m.revision_id=NEW.id AND m.role IN ('original_card','scene') AND m.reveal_stage='question' AND a.availability='local') THEN RAISE EXCEPTION 'Reviewed question media required'; END IF;
 END IF; RETURN NEW; END $$;
CREATE TRIGGER publication_media BEFORE UPDATE ON content.question_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_publish_media();
REVOKE EXECUTE ON FUNCTION content.guard_publish_media() FROM PUBLIC;

CREATE TABLE intelligence.embedding_profiles (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), provider text NOT NULL, model text NOT NULL, model_revision text NOT NULL, dimensions integer NOT NULL CHECK(dimensions>0), distance_metric text NOT NULL CHECK(distance_metric IN ('cosine','l2','inner_product')), preprocessing_version text NOT NULL, UNIQUE(provider,model,model_revision,dimensions,preprocessing_version));
-- Actual vector tables are added with the selected extension/model, not a guessed dimension.
CREATE TABLE intelligence.recommendation_runs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, policy_version text NOT NULL, evidence_cursor uuid REFERENCES learning.learning_events, constraints jsonb NOT NULL, outcome text NOT NULL CHECK(outcome IN ('selected','insufficient_pool','insufficient_evidence')), created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id), UNIQUE(id,tenant_id,membership_id));
CREATE TABLE intelligence.recommendation_items (run_id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL, position integer NOT NULL CHECK(position>0), question_revision_id uuid NOT NULL REFERENCES content.question_revisions, reason_code text NOT NULL, PRIMARY KEY(run_id,position), UNIQUE(run_id,question_revision_id), FOREIGN KEY(run_id,tenant_id,membership_id) REFERENCES intelligence.recommendation_runs(id,tenant_id,membership_id));
CREATE TABLE intelligence.tutor_sessions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, purpose text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), retention_until timestamptz NOT NULL, FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id), UNIQUE(id,tenant_id,membership_id));
ALTER TABLE intelligence.ai_runs ADD UNIQUE(id,tenant_id,membership_id);
CREATE TABLE intelligence.tutor_messages (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), session_id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL, role text NOT NULL CHECK(role IN ('user','assistant')), text text NOT NULL, ai_run_id uuid, created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(session_id,tenant_id,membership_id) REFERENCES intelligence.tutor_sessions(id,tenant_id,membership_id), FOREIGN KEY(ai_run_id,tenant_id,membership_id) REFERENCES intelligence.ai_runs(id,tenant_id,membership_id));
CREATE TABLE intelligence.ai_run_references (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), ai_run_id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL, question_revision_id uuid REFERENCES content.question_revisions, knowledge_chunk_id uuid REFERENCES content.knowledge_chunks, CHECK(num_nonnulls(question_revision_id,knowledge_chunk_id)=1), FOREIGN KEY(ai_run_id,tenant_id,membership_id) REFERENCES intelligence.ai_runs(id,tenant_id,membership_id));
CREATE TABLE intelligence.ai_budget_accounts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL, period_start timestamptz NOT NULL, period_end timestamptz NOT NULL, currency text NOT NULL, budget numeric NOT NULL CHECK(budget>=0), spent numeric NOT NULL DEFAULT 0 CHECK(spent>=0), reserved numeric NOT NULL DEFAULT 0 CHECK(reserved>=0), CHECK(period_end>period_start), CHECK(spent+reserved<=budget), FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id), UNIQUE(tenant_id,membership_id,period_start,currency), UNIQUE(id,tenant_id,membership_id));
CREATE TABLE intelligence.ai_budget_reservations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), account_id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL, ai_run_id uuid, idempotency_key uuid NOT NULL, amount numeric NOT NULL CHECK(amount>=0), settled_amount numeric CHECK(settled_amount>=0), status text NOT NULL DEFAULT 'reserved' CHECK(status IN ('reserved','settled','released')), created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(account_id,tenant_id,membership_id) REFERENCES intelligence.ai_budget_accounts(id,tenant_id,membership_id), FOREIGN KEY(ai_run_id,tenant_id,membership_id) REFERENCES intelligence.ai_runs(id,tenant_id,membership_id), UNIQUE(tenant_id,membership_id,idempotency_key));
-- Budget tables have no runtime writes until the reservation/settlement service exists.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['recommendation_runs','recommendation_items','tutor_sessions','tutor_messages','ai_run_references','ai_budget_accounts','ai_budget_reservations'] LOOP
  EXECUTE format('ALTER TABLE intelligence.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE intelligence.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY learner_scope ON intelligence.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id = nullif(current_setting(''app.membership_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id = nullif(current_setting(''app.membership_id'',true),'''')::uuid)',t);
  EXECUTE format('GRANT SELECT ON intelligence.%I TO sya9a_student_runtime',t);
 END LOOP;
END $$;
CREATE INDEX source_records_batch_idx ON ingestion.source_records(batch_id,source_series_key,source_position);
CREATE INDEX question_source_record_idx ON ingestion.question_sources(source_record_id);
CREATE INDEX question_topic_idx ON content.question_topics(topic_id,revision_id);
CREATE INDEX question_concept_idx ON content.question_concepts(concept_id,approval_status,revision_id);
CREATE INDEX choice_group_idx ON content.choices(group_id);
CREATE INDEX question_media_asset_idx ON content.question_media(asset_id);
CREATE INDEX mastery_learner_idx ON intelligence.mastery_snapshots(tenant_id,membership_id,concept_id,created_at DESC);
CREATE INDEX readiness_learner_idx ON intelligence.readiness_snapshots(tenant_id,membership_id,created_at DESC);
CREATE VIEW content.published_choice_groups AS SELECT g.id,g.revision_id,g.position,g.selection_min,g.selection_max,l.locale,l.label FROM content.choice_groups g JOIN content.choice_group_localizations l ON l.group_id=g.id JOIN content.question_revisions r ON r.id=g.revision_id WHERE r.status='published';
CREATE VIEW content.published_question_media AS SELECT m.revision_id,m.asset_id,m.role,m.locale,m.position,m.alt_text,a.object_key,a.mime FROM content.question_media m JOIN content.media_assets a ON a.id=m.asset_id JOIN content.question_revisions r ON r.id=m.revision_id WHERE r.status='published' AND m.reveal_stage='question' AND a.availability='local';
GRANT SELECT ON content.published_choice_groups,content.published_question_media TO sya9a_student_runtime;
