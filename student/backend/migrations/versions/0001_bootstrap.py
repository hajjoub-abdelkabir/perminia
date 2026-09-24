"""Persist an environment identity; product tables arrive with learner features."""
from alembic import op
import sqlalchemy as sa

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_bootstrap",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instance_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id = 1", name="single_bootstrap_row"),
    )
    op.execute("INSERT INTO app_bootstrap (id) VALUES (1)")


def downgrade():
    op.drop_table("app_bootstrap")
