"""login lockout per (login, client address); login_attempt stays as the per-login ceiling"""

from alembic import op

revision = "0011"
down_revision = "0010_review"


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
    # Production runtime role ilm_app (created by hand, docs/ops/deploy.md): DML only, the
    # audit log append-only, the version table read-only. No such role (CI, dev): skipped.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ilm_app') THEN
            GRANT USAGE ON SCHEMA public TO ilm_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ilm_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ilm_app;
            REVOKE UPDATE, DELETE ON audit_log FROM ilm_app;
            REVOKE ALL ON alembic_version FROM ilm_app;
            GRANT SELECT ON alembic_version TO ilm_app;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE login_ip_attempt")
    op.execute("DROP INDEX login_attempt_updated_idx")
    op.execute("ALTER TABLE login_attempt DROP COLUMN updated_at")
