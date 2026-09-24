"""Preserve reading activity dates independently of latest progress state."""
from pathlib import Path
from alembic import op
revision='0011_journey_history'
down_revision='0010_student_journey'
branch_labels=depends_on=None

def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2]/'schema/0011_journey_history.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Use a forward migration to preserve activity history.')
