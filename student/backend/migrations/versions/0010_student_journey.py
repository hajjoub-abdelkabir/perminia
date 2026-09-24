"""Student journey, ungraded participation and explicitly synthetic performance."""
from pathlib import Path
from alembic import op
revision = '0010_student_journey'
down_revision = '0009_lesson_media'
branch_labels = depends_on = None

def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2]/'schema/0010_student_journey.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Use a forward migration to preserve learner history.')
