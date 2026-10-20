"""attendance cells and grades (stage 1b)"""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    # A lesson with marks cannot be deleted (RESTRICT): the schedule rebuild keeps such lessons,
    # and this is the guarantee behind it. Marks go with their enrollment.
    op.execute(
        """
        CREATE TABLE attendance (
          lesson_id uuid NOT NULL REFERENCES lesson(id) ON DELETE RESTRICT,
          enrollment_id uuid NOT NULL REFERENCES enrollment(id) ON DELETE CASCADE,
          present boolean NOT NULL,
          reason text,
          marked_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
          marked_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (lesson_id, enrollment_id),
          CONSTRAINT attendance_reason_check CHECK (NOT present OR reason IS NULL)
        )
        """
    )
    op.execute("CREATE INDEX attendance_enrollment_idx ON attendance (enrollment_id)")
    op.execute(
        """
        CREATE TABLE grade (
          enrollment_id uuid PRIMARY KEY REFERENCES enrollment(id) ON DELETE CASCADE,
          homework smallint CONSTRAINT grade_homework_check CHECK (homework BETWEEN 0 AND 40),
          final smallint CONSTRAINT grade_final_check CHECK (final BETWEEN 0 AND 40),
          updated_at timestamptz NOT NULL DEFAULT now(),
          version integer NOT NULL DEFAULT 1
        )
        """
    )
    op.execute(
        "CREATE TRIGGER grade_bump_version BEFORE UPDATE ON grade "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE grade")
    op.execute("DROP TABLE attendance")
