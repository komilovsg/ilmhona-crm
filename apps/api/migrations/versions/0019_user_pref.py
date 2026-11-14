"""per-user dashboard preferences (which cards, in which order)"""

from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_pref (
          user_id uuid PRIMARY KEY REFERENCES app_user (id) ON DELETE CASCADE,
          dashboard jsonb NOT NULL DEFAULT '{}'::jsonb CONSTRAINT user_pref_dashboard_check
            CHECK (jsonb_typeof(dashboard) = 'object' AND pg_column_size(dashboard) <= 4096),
          version integer NOT NULL DEFAULT 1,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE TRIGGER user_pref_bump_version BEFORE UPDATE ON user_pref "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE user_pref")
