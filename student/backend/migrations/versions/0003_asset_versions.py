"""Version assets by bytes, not by a mutable remote URL."""
from alembic import op
revision='0003_asset_versions'
down_revision='0002_content'
branch_labels=None
depends_on=None

def upgrade():
    op.drop_constraint('media_assets_source_id_original_url_key','media_assets',schema='content',type_='unique')
    op.create_index('media_source_url_idx','media_assets',['source_id','original_url'],schema='content')
    statement="""
    CREATE FUNCTION content.guard_asset_identity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Archived asset identities are immutable'; END IF;
      IF (to_jsonb(NEW)-'availability') IS DISTINCT FROM (to_jsonb(OLD)-'availability') THEN RAISE EXCEPTION 'Changed media requires a new asset'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER immutable_asset BEFORE UPDATE OR DELETE ON content.media_assets FOR EACH ROW EXECUTE FUNCTION content.guard_asset_identity();
    REVOKE EXECUTE ON FUNCTION content.guard_asset_identity() FROM PUBLIC;
    """
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(statement)

def downgrade():
    raise RuntimeError('Cannot merge historical assets by URL; use a forward migration.')
