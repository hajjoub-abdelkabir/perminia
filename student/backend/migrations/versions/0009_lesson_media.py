"""Hash-bound lesson media with independent local preview review state."""
from pathlib import Path
from alembic import op
revision='0009_lesson_media'
down_revision='0008_lessons'
branch_labels=depends_on=None

def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2]/'schema/0009_lesson_media.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Use a forward migration; source history is retained.')
