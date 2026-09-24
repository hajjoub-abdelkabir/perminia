"""School-owned student activation replaces open registration."""
from pathlib import Path
from alembic import op
revision = '0007_school_invites'
down_revision = '0006_student_accounts'
branch_labels = None
depends_on = None


def upgrade():
    source = Path(__file__).resolve().parents[2] / 'schema' / '0007_school_invites.sql'
    cursor = op.get_bind().connection.driver_connection.cursor()
    try:
        cursor.execute(source.read_text(encoding='utf-8-sig'))
    finally:
        cursor.close()


def downgrade():
    raise RuntimeError('School memberships and invitations are user data; use a forward migration.')
