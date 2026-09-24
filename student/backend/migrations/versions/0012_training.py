"""Resumable practice with authoritative deadlines and review-gated evaluation."""
from pathlib import Path
from alembic import op
revision='0012_training'
down_revision='0011_journey_history'
branch_labels=depends_on=None
def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2]/'schema/0012_training.sql').read_text(encoding='utf-8'))
def downgrade():
    raise RuntimeError('Preserve training evidence with a forward migration.')
