"""sessions (device, last use, remember me) and password reset requests"""

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE refresh_token
          ADD COLUMN user_agent text,
          ADD COLUMN last_used_at timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN remember boolean NOT NULL DEFAULT true
        """
    )
    op.execute(
        """
        CREATE TABLE password_reset_request (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          login citext NOT NULL,
          user_id uuid REFERENCES app_user (id) ON DELETE CASCADE,
          created_at timestamptz NOT NULL DEFAULT now(),
          ip text NOT NULL,
          status text NOT NULL DEFAULT 'новый'
            CHECK (status IN ('новый', 'выполнен', 'отклонён')),
          handled_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          handled_at timestamptz
        )
        """
    )
    op.execute(
        "CREATE INDEX password_reset_request_login_idx "
        "ON password_reset_request (login, created_at)"
    )
    op.execute(
        "CREATE INDEX password_reset_request_ip_idx ON password_reset_request (ip, created_at)"
    )
    op.execute(
        "CREATE INDEX password_reset_request_open_idx ON password_reset_request (user_id) "
        "WHERE status = 'новый'"
    )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ilm_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_request TO ilm_app;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE password_reset_request")
    op.execute(
        "ALTER TABLE refresh_token DROP COLUMN user_agent, DROP COLUMN last_used_at, "
        "DROP COLUMN remember"
    )
