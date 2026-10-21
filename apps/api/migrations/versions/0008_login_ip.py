"""login lockout per (login, client address); login_attempt stays as the per-login ceiling"""

from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.execute("ALTER TABLE login_attempt ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()")
    op.execute(
        """
        CREATE TABLE login_ip_attempt (
          login citext NOT NULL,
          ip text NOT NULL,
          failures integer NOT NULL DEFAULT 0,
          locked_until timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (login, ip)
        )
        """
    )
    op.execute("CREATE INDEX login_ip_attempt_updated_idx ON login_ip_attempt (updated_at)")
    op.execute("CREATE INDEX login_attempt_updated_idx ON login_attempt (updated_at)")


def downgrade() -> None:
    op.execute("DROP TABLE login_ip_attempt")
    op.execute("DROP INDEX login_attempt_updated_idx")
    op.execute("ALTER TABLE login_attempt DROP COLUMN updated_at")
