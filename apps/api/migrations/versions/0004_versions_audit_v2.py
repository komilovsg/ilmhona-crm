"""row versions for edit conflicts (#25), audit label"""

from alembic import op

revision = "0004"
down_revision = "0003"

TABLES = ("app_user", "role", "room", "course", "cohort", "lesson", "student", "enrollment")


def upgrade() -> None:
    # One trigger, one rule: any real change of a row (by an endpoint, a job, a bulk update)
    # bumps its version. A no-op UPDATE changes nothing. `touch` in app/core/versioning.py
    # bumps a row whose change lives in a child table (the role's permission matrix).
    op.execute(
        """
        CREATE FUNCTION bump_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          NEW.version := OLD.version + 1;
          RETURN NEW;
        END $$
        """
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN version integer NOT NULL DEFAULT 1")
        op.execute(
            f"CREATE TRIGGER {table}_bump_version BEFORE UPDATE ON {table} "
            "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
        )
    # the display name of the changed row, as it was when the entry was written
    op.execute("ALTER TABLE audit_log ADD COLUMN label text")


def downgrade() -> None:
    op.execute("ALTER TABLE audit_log DROP COLUMN label")
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_bump_version ON {table}")
        op.execute(f"ALTER TABLE {table} DROP COLUMN version")
    op.execute("DROP FUNCTION bump_version()")
