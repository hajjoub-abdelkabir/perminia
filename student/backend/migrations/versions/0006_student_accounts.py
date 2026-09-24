"""Student accounts and revocable sessions; no runtime access to base tables."""
from alembic import op
from pathlib import Path
revision = '0006_student_accounts'
down_revision = '0005_student_preview'
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[2] / 'schema' / '0006_student_accounts.sql').read_text(encoding='utf-8-sig')
    cursor = op.get_bind().connection.driver_connection.cursor()
    try:
        cursor.execute(sql)
    finally:
        cursor.close()


def downgrade():
    raise RuntimeError('Accounts contain user data; use a forward migration.')
