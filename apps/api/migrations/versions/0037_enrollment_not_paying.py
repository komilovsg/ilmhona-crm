"""enrollment not paying: `enrollment.not_paying`, a student marked by hand as studying for free

Set per student in a «платный» or «смешанный» cohort (e.g. a graduate of a donor course who gets
the next course for free). Such a student owes nothing and no payment is taken, like a
donor-funded one, but no donor pays for them: the two never go together.
"""

from alembic import op

revision = "0037"
down_revision = "0036"


def upgrade() -> None:
    op.execute("ALTER TABLE enrollment ADD COLUMN not_paying boolean NOT NULL DEFAULT false")
    op.execute(
        "ALTER TABLE enrollment ADD CONSTRAINT enrollment_not_paying_donor_check "
        "CHECK (NOT (not_paying AND donor_id IS NOT NULL))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE enrollment DROP COLUMN not_paying")
