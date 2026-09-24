CREATE TABLE intelligence.chat_threads (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES identity.tenants,
 membership_id uuid NOT NULL REFERENCES identity.memberships,
 title text NOT NULL DEFAULT 'محادثة جديدة' CHECK(length(title)<=100),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 consent_version text NOT NULL DEFAULT 'chat-v1',
 UNIQUE(id,tenant_id,membership_id),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id)
);
CREATE TABLE intelligence.chat_turns (
 id uuid PRIMARY KEY, thread_id uuid NOT NULL,
 tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 question text NOT NULL CHECK(length(question) BETWEEN 1 AND 1500),
 answer text CHECK(length(answer)<=6000),
 sources jsonb NOT NULL DEFAULT '[]',
 status text NOT NULL CHECK(status IN ('pending','complete','failed')),
 provider text, model text, input_tokens integer, output_tokens integer,
 created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 FOREIGN KEY(thread_id,tenant_id,membership_id) REFERENCES intelligence.chat_threads(id,tenant_id,membership_id) ON DELETE CASCADE
);
CREATE INDEX chat_threads_owner ON intelligence.chat_threads(membership_id,updated_at DESC);
CREATE INDEX chat_turns_thread ON intelligence.chat_turns(thread_id,created_at,id);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['chat_threads','chat_turns'] LOOP
  EXECUTE 'ALTER TABLE intelligence.'||t||' ENABLE ROW LEVEL SECURITY';
  EXECUTE 'ALTER TABLE intelligence.'||t||' FORCE ROW LEVEL SECURITY';
  EXECUTE 'CREATE POLICY chat_owner ON intelligence.'||t||' USING(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id=nullif(current_setting(''app.membership_id'',true),'''')::uuid) WITH CHECK(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid AND membership_id=nullif(current_setting(''app.membership_id'',true),'''')::uuid)';
 END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE,DELETE ON intelligence.chat_threads,intelligence.chat_turns TO sya9a_student_runtime;
-- No message content here. Deleting a conversation cannot reset paid-call limits.
CREATE TABLE intelligence.chat_budget (
 bucket text NOT NULL, day date NOT NULL DEFAULT CURRENT_DATE, used integer NOT NULL DEFAULT 0,
 PRIMARY KEY(bucket,day)
);
REVOKE ALL ON intelligence.chat_budget FROM PUBLIC,sya9a_student_runtime;
CREATE FUNCTION intelligence.reserve_chat_budget(p_user_cap integer,p_global_cap integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE m uuid; t uuid; n integer;
BEGIN
 m:=nullif(current_setting('app.membership_id',true),'')::uuid;
 t:=nullif(current_setting('app.tenant_id',true),'')::uuid;
 IF m IS NULL OR NOT EXISTS(SELECT 1 FROM identity.memberships WHERE id=m AND tenant_id=t) THEN RETURN false; END IF;
 -- Serialize reservations across workers and schools; no provider network call holds this lock.
 PERFORM pg_advisory_xact_lock(716162221);
 INSERT INTO intelligence.chat_budget(bucket) VALUES('global'),('member:'||m) ON CONFLICT DO NOTHING;
 SELECT used INTO n FROM intelligence.chat_budget WHERE bucket='global' AND day=CURRENT_DATE;
 IF n>=least(greatest(p_global_cap,0),1000) THEN RETURN false; END IF;
 SELECT used INTO n FROM intelligence.chat_budget WHERE bucket='member:'||m AND day=CURRENT_DATE;
 IF n>=least(greatest(p_user_cap,0),100) THEN RETURN false; END IF;
 UPDATE intelligence.chat_budget SET used=used+1 WHERE day=CURRENT_DATE AND bucket IN ('global','member:'||m);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION intelligence.reserve_chat_budget(integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION intelligence.reserve_chat_budget(integer,integer) TO sya9a_student_runtime;
