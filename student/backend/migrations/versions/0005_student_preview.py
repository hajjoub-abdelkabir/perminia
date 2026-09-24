"""Read-only local preview, deliberately excludes answers and explanations."""
from alembic import op

revision = '0005_student_preview'
down_revision = '0004_audio_metadata'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE VIEW content.preview_series AS
    SELECT a.id, a.source_key, a.title, r.id AS revision_id, r.item_count
    FROM content.assessments a
    JOIN content.assessment_revisions r ON r.assessment_id=a.id
    WHERE a.kind='source_series' AND r.status IN ('draft','published')
      AND r.revision_number=(SELECT max(n.revision_number) FROM content.assessment_revisions n WHERE n.assessment_id=a.id);

    CREATE VIEW content.preview_questions AS
    SELECT s.id AS series_id, i.position, q.id AS revision_id, q.response_type,
      l.prompt,
      (SELECT jsonb_agg(jsonb_build_object('id',c.id,'number',c.source_choice_number,
        'text',cl.text,'group_id',c.group_id) ORDER BY c.display_position)
       FROM content.choices c JOIN content.choice_localizations cl ON cl.choice_id=c.id AND cl.locale='ary-MA'
       WHERE c.revision_id=q.id) AS choices,
      (SELECT jsonb_agg(jsonb_build_object('id',g.id,'label',gl.label) ORDER BY g.position)
       FROM content.choice_groups g LEFT JOIN content.choice_group_localizations gl ON gl.group_id=g.id AND gl.locale='ary-MA'
       WHERE g.revision_id=q.id) AS groups
    FROM content.preview_series s
    JOIN content.assessment_items i ON i.assessment_revision_id=s.revision_id
    JOIN content.question_revisions q ON q.id=i.question_revision_id
    JOIN content.question_localizations l ON l.revision_id=q.id AND l.locale='ary-MA'
    WHERE q.status IN ('draft','published');

    CREATE VIEW content.preview_media AS
    SELECT DISTINCT q.revision_id, m.asset_id, m.role, m.position,
      a.object_key, a.mime, a.duration_seconds
    FROM content.preview_questions q
    JOIN content.question_media m ON m.revision_id=q.revision_id
    JOIN content.media_assets a ON a.id=m.asset_id
    WHERE m.role IN ('original_card','audio') AND m.locale='ary-MA' AND a.availability='local';

    GRANT SELECT ON content.preview_series,content.preview_questions,content.preview_media TO sya9a_student_runtime;
    """)


def downgrade():
    op.execute('DROP VIEW content.preview_media,content.preview_questions,content.preview_series')
