CREATE TABLE learning.reading_activity (
 tenant_id uuid NOT NULL, membership_id uuid NOT NULL, revision_id uuid NOT NULL,
 section_position integer NOT NULL, day date NOT NULL,
 origin text NOT NULL CHECK(origin IN ('completion','latest_state_backfill')),
 PRIMARY KEY(tenant_id,membership_id,revision_id,section_position,day),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id),
 FOREIGN KEY(revision_id,section_position) REFERENCES content.lesson_sections(revision_id,position)
);
ALTER TABLE learning.reading_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning.reading_activity FORCE ROW LEVEL SECURITY;
CREATE POLICY learner_scope ON learning.reading_activity
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND membership_id=nullif(current_setting('app.membership_id',true),'')::uuid);
GRANT SELECT ON learning.reading_activity TO sya9a_student_runtime;
INSERT INTO learning.reading_activity SELECT tenant_id,membership_id,revision_id,section_position,
 (updated_at AT TIME ZONE 'Africa/Casablanca')::date,'latest_state_backfill' FROM learning.lesson_section_progress WHERE completed;
CREATE FUNCTION learning.record_reading_activity() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF NEW.completed AND (TG_OP='INSERT' OR OLD.completed IS DISTINCT FROM NEW.completed) THEN
  INSERT INTO learning.reading_activity VALUES(NEW.tenant_id,NEW.membership_id,NEW.revision_id,NEW.section_position,
   (now() AT TIME ZONE 'Africa/Casablanca')::date,'completion') ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION learning.record_reading_activity() FROM PUBLIC;
CREATE TRIGGER keep_reading_history AFTER INSERT OR UPDATE ON learning.lesson_section_progress FOR EACH ROW EXECUTE FUNCTION learning.record_reading_activity();
INSERT INTO learning.journey_profiles(tenant_id,membership_id,enrolled_on)
 SELECT p.tenant_id,p.membership_id,(u.created_at AT TIME ZONE 'Africa/Casablanca')::date
 FROM identity.learner_profiles p JOIN identity.memberships m ON m.id=p.membership_id JOIN identity.users u ON u.id=m.user_id
 ON CONFLICT DO NOTHING;
CREATE FUNCTION learning.start_student_journey() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 INSERT INTO learning.journey_profiles(tenant_id,membership_id) VALUES(NEW.tenant_id,NEW.membership_id) ON CONFLICT DO NOTHING;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION learning.start_student_journey() FROM PUBLIC;
CREATE TRIGGER start_journey AFTER INSERT ON identity.learner_profiles FOR EACH ROW EXECUTE FUNCTION learning.start_student_journey();
