"""one instructor, one lesson at a time: lesson.instructor_id + EXCLUDE (instructor × time)

The cohort's instructor is copied onto each lesson (a trigger fills it on insert; the API moves
the lessons still ahead when a cohort changes its instructor), so the database can refuse two
overlapping live lessons of one instructor, across rooms, cohorts and branches.

Real imported data may already hold such overlaps, and EXCLUDE has no NOT VALID. So before the
constraint is added, every live lesson that overlaps another live lesson of the same instructor
(both sides, any date) is marked `instructor_conflict`; marked lessons are outside the constraint
and the cohort shows «Проверить: конфликт инструктора». The mark goes away when the overlap is
resolved (a lesson moved or cancelled, the instructor changed); a moved lesson loses its mark and
is checked like any other. Nothing new can be marked by the API: only this migration and the
import mark lessons.
"""

from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE lesson ADD COLUMN instructor_id uuid REFERENCES app_user (id), "
        "ADD COLUMN instructor_conflict boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "UPDATE lesson l SET instructor_id = c.instructor_id FROM cohort c "
        "WHERE c.id = l.cohort_id AND c.instructor_id IS NOT NULL"
    )
    op.execute("CREATE INDEX lesson_instructor_idx ON lesson (instructor_id, starts_at)")
    # the overlaps that are already there: marked on both sides, kept out of the constraint
    op.execute(
        """
        UPDATE lesson l SET instructor_conflict = true
        WHERE NOT l.cancelled AND l.instructor_id IS NOT NULL AND EXISTS (
          SELECT 1 FROM lesson o
          WHERE o.instructor_id = l.instructor_id AND o.id <> l.id AND NOT o.cancelled
            AND o.starts_at < l.ends_at AND o.ends_at > l.starts_at)
        """
    )
    op.execute(
        """
        CREATE FUNCTION lesson_instructor_fill() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          NEW.instructor_id := (SELECT instructor_id FROM cohort WHERE id = NEW.cohort_id);
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER lesson_instructor_fill BEFORE INSERT ON lesson "
        "FOR EACH ROW EXECUTE FUNCTION lesson_instructor_fill()"
    )
    op.execute(
        """
        ALTER TABLE lesson ADD CONSTRAINT lesson_instructor_no_overlap EXCLUDE USING gist (
          instructor_id WITH =, tstzrange(starts_at, ends_at) WITH &&)
          WHERE (NOT cancelled AND NOT instructor_conflict AND instructor_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE lesson DROP CONSTRAINT lesson_instructor_no_overlap")
    op.execute("DROP TRIGGER lesson_instructor_fill ON lesson")
    op.execute("DROP FUNCTION lesson_instructor_fill()")
    op.execute("DROP INDEX lesson_instructor_idx")
    op.execute("ALTER TABLE lesson DROP COLUMN instructor_conflict, DROP COLUMN instructor_id")
