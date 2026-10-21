"""legacy_ref: where an imported row came from in the old system (stage 5)"""

from alembic import op

revision = "0009"
down_revision = "0008"

TABLES = (
    "room",
    "course",
    "app_user",
    "cohort",
    "lesson",
    "student",
    "enrollment",
    "payment",
    "instructor_payout",
    "campaign",
    "lead",
)


def upgrade() -> None:
    # nullable: rows made in the app have none. The import finds its own rows by it (a re-run
    # adds nothing twice) and never touches a row without it.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN legacy_ref text")
        op.execute(f"CREATE UNIQUE INDEX {table}_legacy_ref_key ON {table} (legacy_ref)")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP INDEX {table}_legacy_ref_key")
        op.execute(f"ALTER TABLE {table} DROP COLUMN legacy_ref")
