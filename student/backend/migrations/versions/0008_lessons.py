"""Versioned local lesson preview and tenant-isolated section progress."""
from pathlib import Path
from alembic import op
revision = '0008_lessons'
down_revision = '0007_school_invites'
branch_labels = depends_on = None

def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2] / 'schema/0008_lessons.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Restore a backup or use a forward migration; learner history is persistent.')
