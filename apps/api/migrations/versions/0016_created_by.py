"""who added a student / an enrollment: student.created_by, enrollment.created_by

An instructor may remove only the enrollments (and students) they added themselves, so both
rows remember their author. Null for rows from before this column and for imported rows.
"""

from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    for table in ("student", "enrollment"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN created_by uuid "
            "REFERENCES app_user (id) ON DELETE SET NULL"
        )


def downgrade() -> None:
    for table in ("student", "enrollment"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN created_by")
