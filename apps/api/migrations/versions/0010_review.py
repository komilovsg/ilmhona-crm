"""review flags on students and enrollments, the old total of an enrollment (stage 5)"""

from alembic import op

revision = "0010_review"
down_revision = "0009"


def upgrade() -> None:
    # The import marks what a person has to look at (no phone, a merge to check, an enrollment
    # restored from a payment ...); a manager clears the flag by hand.
    for table in ("student", "enrollment"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN needs_review boolean NOT NULL DEFAULT false, "
            f"ADD COLUMN review_reason text, "
            f"ADD CONSTRAINT {table}_review_reason_check "
            f"CHECK (needs_review OR review_reason IS NULL)"
        )
        op.execute(f"CREATE INDEX {table}_needs_review_idx ON {table} (id) WHERE needs_review")
    # the total of the old system when it came without homework and final (shown as «итог из
    # старой системы» until real grades are entered)
    op.execute(
        "ALTER TABLE enrollment ADD COLUMN legacy_total numeric(5, 1) "
        "CONSTRAINT enrollment_legacy_total_check CHECK (legacy_total BETWEEN 0 AND 100)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE enrollment DROP COLUMN legacy_total")
    for table in ("enrollment", "student"):
        op.execute(f"DROP INDEX {table}_needs_review_idx")
        op.execute(f"ALTER TABLE {table} DROP COLUMN needs_review, DROP COLUMN review_reason")
