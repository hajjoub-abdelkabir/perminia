CREATE TABLE learning.journey_profiles (
 tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 enrolled_on date NOT NULL DEFAULT CURRENT_DATE, exam_on date,
 daily_minutes integer NOT NULL DEFAULT 20 CHECK(daily_minutes BETWEEN 5 AND 120),
 fixture_version text, persona text,
 PRIMARY KEY(tenant_id,membership_id),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id),
 CHECK(exam_on IS NULL OR exam_on >= enrolled_on)
);
-- Fixture scores cannot be inserted or updated by the API runtime. They are never examination results.
CREATE TABLE learning.demo_performance (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 fixture_version text NOT NULL, occurred_at timestamptz NOT NULL,
 lesson_id uuid NOT NULL REFERENCES content.lessons,
 correct integer NOT NULL, total integer NOT NULL CHECK(total>0),
 minutes integer NOT NULL CHECK(minutes>0), CHECK(correct BETWEEN 0 AND total),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id)
);
CREATE INDEX demo_performance_member_time ON learning.demo_performance(tenant_id,membership_id,occurred_at DESC);
CREATE TABLE learning.preview_sessions (
 id uuid NOT NULL, tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 series_id uuid NOT NULL REFERENCES content.assessments(id),
 outcomes jsonb NOT NULL CHECK(jsonb_typeof(outcomes)='array'),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,membership_id,id),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id)
);
CREATE INDEX preview_sessions_member_time ON learning.preview_sessions(tenant_id,membership_id,recorded_at DESC);
CREATE TABLE intelligence.coach_reports (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 input_hash text NOT NULL, intent text NOT NULL, day date NOT NULL DEFAULT CURRENT_DATE,
 status text NOT NULL CHECK(status IN ('pending','complete','failed')),
 model text NOT NULL, answer text, input_tokens integer, output_tokens integer,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,membership_id,input_hash,intent,day),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['learning.journey_profiles','learning.demo_performance','learning.preview_sessions','intelligence.coach_reports'] LOOP
  EXECUTE 'ALTER TABLE '||t||' ENABLE ROW LEVEL SECURITY';
  EXECUTE 'ALTER TABLE '||t||' FORCE ROW LEVEL SECURITY';
  EXECUTE 'CREATE POLICY learner_scope ON '||t||' USING(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id=nullif(current_setting(''app.membership_id'',true),'''')::uuid) WITH CHECK(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id=nullif(current_setting(''app.membership_id'',true),'''')::uuid)';
 END LOOP;
END $$;
GRANT SELECT ON learning.journey_profiles,learning.demo_performance,learning.preview_sessions,intelligence.coach_reports TO sya9a_student_runtime;
GRANT INSERT(tenant_id,membership_id,exam_on,daily_minutes) ON learning.journey_profiles TO sya9a_student_runtime;
GRANT UPDATE(exam_on,daily_minutes) ON learning.journey_profiles TO sya9a_student_runtime;
GRANT INSERT ON learning.preview_sessions,intelligence.coach_reports TO sya9a_student_runtime;
GRANT UPDATE(status,answer,input_tokens,output_tokens) ON intelligence.coach_reports TO sya9a_student_runtime;
