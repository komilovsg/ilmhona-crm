"""stale cohorts: lessons freed by a finish, and the academy settings row

`lesson.cancelled_by_finish` marks the lessons a finish cancelled (after the finish date, no
attendance marks) so that reopening restores exactly those. `academy_settings` (one row, id = 1)
holds `stale_days`: an активный cohort with no attendance marks for that many days is closed by
the nightly job.
"""

from alembic import op

revision = "0032"
down_revision = "0029"


def upgrade() -> None:
    op.execute("ALTER TABLE lesson ADD COLUMN cancelled_by_finish boolean NOT NULL DEFAULT false")
    op.execute(
        "ALTER TABLE lesson ADD CONSTRAINT lesson_finish_cancel_check "
        "CHECK (NOT cancelled_by_finish OR cancelled)"
    )
    op.execute(
        "CREATE INDEX lesson_cancelled_by_finish_idx ON lesson (cohort_id) "
        "WHERE cancelled_by_finish"
    )
    op.execute(
        """
        CREATE TABLE academy_settings (
          id smallint PRIMARY KEY DEFAULT 1 CONSTRAINT academy_settings_single_row CHECK (id = 1),
          stale_days integer NOT NULL DEFAULT 60
            CONSTRAINT academy_settings_stale_days_check CHECK (stale_days BETWEEN 20 AND 730),
          version integer NOT NULL DEFAULT 1,
          updated_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE TRIGGER academy_settings_bump_version BEFORE UPDATE ON academy_settings "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )
    op.execute("INSERT INTO academy_settings (id) VALUES (1)")


def downgrade() -> None:
    op.execute("DROP TABLE academy_settings")
    op.execute("DROP INDEX lesson_cancelled_by_finish_idx")
    op.execute("ALTER TABLE lesson DROP COLUMN cancelled_by_finish")
