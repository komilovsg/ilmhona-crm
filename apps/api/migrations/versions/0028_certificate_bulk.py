"""certificate bulk issue: a certificate without an enrollment

A certificate issued from an Excel list belongs to a person who may not be a student: it has no
enrollment, cohort or course, only a branch, an optional linked student and the batch it came in
with. A row is either an enrollment certificate (all three set) or a batch one.
"""

from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE certificate
          ALTER COLUMN enrollment_id DROP NOT NULL,
          ALTER COLUMN cohort_id DROP NOT NULL,
          ALTER COLUMN course_id DROP NOT NULL,
          ADD COLUMN student_id uuid REFERENCES student (id) ON DELETE SET NULL,
          ADD COLUMN batch_id uuid
        """
    )
    op.execute(
        "ALTER TABLE certificate ADD CONSTRAINT certificate_source_check "
        "CHECK (batch_id IS NOT NULL OR "
        "(enrollment_id IS NOT NULL AND cohort_id IS NOT NULL AND course_id IS NOT NULL))"
    )
    op.execute(
        "CREATE INDEX certificate_batch_idx ON certificate (batch_id) WHERE batch_id IS NOT NULL"
    )
    op.execute("CREATE INDEX certificate_student_idx ON certificate (student_id)")


def downgrade() -> None:
    # certificates of a batch have no enrollment to go back to: they are dropped
    op.execute(
        "UPDATE certificate SET replaced_by_id = NULL WHERE replaced_by_id IN "
        "(SELECT id FROM certificate WHERE batch_id IS NOT NULL)"
    )
    op.execute("DELETE FROM certificate WHERE batch_id IS NOT NULL")
    op.execute("ALTER TABLE certificate DROP CONSTRAINT certificate_source_check")
    op.execute("DROP INDEX certificate_batch_idx")
    op.execute("DROP INDEX certificate_student_idx")
    op.execute(
        """
        ALTER TABLE certificate
          DROP COLUMN batch_id,
          DROP COLUMN student_id,
          ALTER COLUMN enrollment_id SET NOT NULL,
          ALTER COLUMN cohort_id SET NOT NULL,
          ALTER COLUMN course_id SET NOT NULL
        """
    )
