from pathlib import Path
from alembic import op
revision='0014_school_mvp'
down_revision='0013_notebook'
branch_labels=depends_on=None

def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2]/'schema/0014_school_mvp.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Preserve school assignments and history with a forward migration.')
