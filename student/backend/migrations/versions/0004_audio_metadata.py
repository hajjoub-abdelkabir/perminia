"""Metadata for validated local question audio."""
from alembic import op
import sqlalchemy as sa
revision='0004_audio_metadata'
down_revision='0003_asset_versions'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('media_assets',sa.Column('duration_seconds',sa.Numeric(),nullable=True),schema='content')
    op.add_column('media_assets',sa.Column('audio_sample_rate',sa.Integer(),nullable=True),schema='content')
    op.add_column('media_assets',sa.Column('audio_channels',sa.Integer(),nullable=True),schema='content')
    op.create_check_constraint('valid_audio_metadata','media_assets',"(duration_seconds IS NULL AND audio_sample_rate IS NULL AND audio_channels IS NULL) OR (mime='audio/mpeg' AND duration_seconds IS NOT NULL AND duration_seconds>0 AND audio_sample_rate IS NOT NULL AND audio_sample_rate>0 AND audio_channels IS NOT NULL AND audio_channels IN (1,2))",schema='content')

def downgrade():
    raise RuntimeError('Preserve imported media metadata; use a forward migration.')
