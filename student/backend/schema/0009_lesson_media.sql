CREATE TABLE content.lesson_media (
 revision_id uuid NOT NULL,
 section_position integer NOT NULL,
 asset_id uuid NOT NULL REFERENCES content.media_assets,
 source_key text NOT NULL,
 concept_key text NOT NULL,
 source_text_hash text NOT NULL,
 display_order integer NOT NULL CHECK(display_order>0),
 review_state text NOT NULL CHECK(review_state IN ('preview','hold','published')),
 metadata jsonb NOT NULL,
 PRIMARY KEY(revision_id,section_position,asset_id),
 FOREIGN KEY(revision_id,section_position) REFERENCES content.lesson_sections(revision_id,position)
);
CREATE VIEW content.preview_lesson_media AS
 SELECT m.*,a.object_key,a.mime FROM content.lesson_media m
 JOIN content.preview_lesson_sections s ON s.revision_id=m.revision_id AND s.position=m.section_position
 JOIN content.media_assets a ON a.id=m.asset_id
 WHERE m.review_state IN ('preview','published') AND a.availability='local';
GRANT SELECT ON content.preview_lesson_media TO sya9a_student_runtime;
