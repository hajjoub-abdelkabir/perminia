"""Versioned question bank, provenance, assessment and learner evidence foundation."""
from pathlib import Path
from alembic import op
revision = '0002_content'
down_revision = '0001_bootstrap'
branch_labels = None
depends_on = None

def upgrade():
    sql = (Path(__file__).resolve().parents[2] / 'schema' / '0002_content.sql').read_text(encoding='utf-8-sig')
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(sql)

def downgrade():
    raise RuntimeError('Content history is persistent. Restore a verified backup or use a forward migration.')
