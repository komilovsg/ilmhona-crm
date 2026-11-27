"""attendance: «уважительная» flag

An excused absence is left out of the held count (app.metrics.attendance). The flag only exists
on an absence. Marks the journal import already wrote with the reason «уважительная причина»
become excused.
"""

from alembic import op

revision = "0029"
down_revision = "0028"


def upgrade() -> None:
    op.execute("ALTER TABLE attendance ADD COLUMN excused boolean NOT NULL DEFAULT false")
    op.execute(
        "UPDATE attendance SET excused = true WHERE NOT present AND reason = 'уважительная причина'"
    )
    op.execute(
        "ALTER TABLE attendance ADD CONSTRAINT attendance_excused_absent_check "
        "CHECK (NOT (excused AND present))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE attendance DROP CONSTRAINT attendance_excused_absent_check")
    op.execute("ALTER TABLE attendance DROP COLUMN excused")
