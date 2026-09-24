CREATE TABLE content.lessons (
 id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES ingestion.content_sources,
 source_key text NOT NULL, slug text NOT NULL UNIQUE, position integer NOT NULL CHECK(position>0),
 UNIQUE(source_id,source_key)
);
CREATE TABLE content.lesson_revisions (
 id uuid PRIMARY KEY, lesson_id uuid NOT NULL REFERENCES content.lessons,
 source_record_id uuid NOT NULL REFERENCES ingestion.source_records,
 content_hash text NOT NULL, title_ar text NOT NULL, summary_darija text NOT NULL,
 common_mistakes_darija text NOT NULL, coach_tip text NOT NULL,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','retired')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(lesson_id,content_hash)
);
CREATE TABLE content.lesson_sections (
 revision_id uuid NOT NULL REFERENCES content.lesson_revisions, position integer NOT NULL CHECK(position>0),
 title_ar text NOT NULL, body_darija text NOT NULL, PRIMARY KEY(revision_id,position)
);
CREATE TABLE content.road_sign_revisions (
 id uuid PRIMARY KEY, source_record_id uuid NOT NULL REFERENCES ingestion.source_records,
 source_key text NOT NULL, slug text NOT NULL, section_name text NOT NULL,
 title_ar text NOT NULL, meaning_darija text NOT NULL, asset_id uuid NOT NULL REFERENCES content.media_assets,
 content_hash text NOT NULL, status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','retired')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_key,content_hash)
);
CREATE TABLE learning.lesson_section_progress (
 tenant_id uuid NOT NULL, membership_id uuid NOT NULL, revision_id uuid NOT NULL,
 section_position integer NOT NULL, completed boolean NOT NULL DEFAULT false, bookmarked boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,membership_id,revision_id,section_position),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id),
 FOREIGN KEY(revision_id,section_position) REFERENCES content.lesson_sections(revision_id,position)
);
ALTER TABLE learning.lesson_section_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning.lesson_section_progress FORCE ROW LEVEL SECURITY;
CREATE POLICY learner_scope ON learning.lesson_section_progress
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND membership_id=nullif(current_setting('app.membership_id',true),'')::uuid)
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND membership_id=nullif(current_setting('app.membership_id',true),'')::uuid);
GRANT SELECT,INSERT,UPDATE ON learning.lesson_section_progress TO sya9a_student_runtime;
CREATE VIEW content.preview_lessons AS
 SELECT DISTINCT ON(l.id) l.id,l.slug,l.position,r.id AS revision_id,r.title_ar,r.summary_darija,
 r.common_mistakes_darija,r.coach_tip,r.status,
 (SELECT count(*) FROM content.lesson_sections s WHERE s.revision_id=r.id) AS section_count
 FROM content.lessons l JOIN content.lesson_revisions r ON r.lesson_id=l.id
 WHERE r.status IN ('draft','published') ORDER BY l.id,r.created_at DESC,r.id;
CREATE VIEW content.preview_lesson_sections AS
 SELECT s.* FROM content.lesson_sections s JOIN content.preview_lessons l ON l.revision_id=s.revision_id;
CREATE VIEW content.preview_signs AS
 SELECT DISTINCT ON(s.source_key) s.id,s.source_key,s.slug,s.section_name,s.title_ar,s.meaning_darija,s.asset_id,
 a.object_key,a.mime FROM content.road_sign_revisions s JOIN content.media_assets a ON a.id=s.asset_id
 WHERE s.status IN ('draft','published') AND a.availability='local' ORDER BY s.source_key,s.created_at DESC,s.id;
GRANT SELECT ON content.preview_lessons,content.preview_lesson_sections,content.preview_signs TO sya9a_student_runtime;
-- Source bodies are immutable; editorial corrections are new revisions. Publication is a later reviewed workflow.
CREATE FUNCTION content.guard_lesson_body() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'Lesson and sign content is immutable; import a new revision';
END $$;
CREATE TRIGGER immutable_lesson BEFORE UPDATE OR DELETE ON content.lesson_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_lesson_body();
CREATE TRIGGER immutable_section BEFORE UPDATE OR DELETE ON content.lesson_sections FOR EACH ROW EXECUTE FUNCTION content.guard_lesson_body();
CREATE TRIGGER immutable_sign BEFORE UPDATE OR DELETE ON content.road_sign_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_lesson_body();
