from pathlib import Path
from alembic import op
revision='0013_notebook'
down_revision='0012_training'
branch_labels=depends_on=None
def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as c:
        c.execute((Path(__file__).resolve().parents[2]/'schema/0013_notebook.sql').read_text(encoding='utf-8'))
def downgrade():
    raise RuntimeError('Preserve personal review history with a forward migration.')
