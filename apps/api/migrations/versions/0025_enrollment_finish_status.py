"""enrollment status before a manual cohort finish

Finishing a cohort closes its active enrollments; the status they had is kept here so that
reopening the cohort restores it exactly.
"""

from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade() -> None:
    op.execute("ALTER TABLE enrollment ADD COLUMN status_before_finish text")


def downgrade() -> None:
    op.execute("ALTER TABLE enrollment DROP COLUMN status_before_finish")
