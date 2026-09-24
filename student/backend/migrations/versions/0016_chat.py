from pathlib import Path
from alembic import op
revision = '0016_chat'
down_revision = '0015_account_recovery'
branch_labels = depends_on = None

def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2]/'schema/0016_chat.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Preserve private conversations; use a forward migration.')
