"""academy goal (one row), goals with automatic progress, private notes"""

from alembic import op

revision = "0018"
down_revision = "0017"

METRICS = (
    "graduates_total",
    "active_students",
    "collection_rate_month",
    "income",
    "new_enrollments",
    "courses_launched",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE academy_goal (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          singleton boolean NOT NULL DEFAULT true UNIQUE CONSTRAINT academy_goal_singleton_check
            CHECK (singleton),
          text text NOT NULL DEFAULT '' CONSTRAINT academy_goal_text_check
            CHECK (char_length(text) <= 280),
          updated_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          version integer NOT NULL DEFAULT 1
        )
        """
    )
    op.execute("INSERT INTO academy_goal DEFAULT VALUES")
    metrics = ", ".join(f"'{m}'" for m in METRICS)
    op.execute(
        f"""
        CREATE TABLE goal (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          title text NOT NULL CONSTRAINT goal_title_check
            CHECK (char_length(title) BETWEEN 1 AND 120),
          metric text NOT NULL CONSTRAINT goal_metric_check CHECK (metric IN ({metrics})),
          target numeric(14, 2) NOT NULL CONSTRAINT goal_target_check CHECK (target > 0),
          baseline numeric(14, 2) NOT NULL DEFAULT 0 CONSTRAINT goal_baseline_check
            CHECK (baseline >= 0),
          start_date date NOT NULL,
          deadline date NOT NULL,
          branch_id uuid REFERENCES branch (id),
          archived boolean NOT NULL DEFAULT false,
          created_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          version integer NOT NULL DEFAULT 1,
          CONSTRAINT goal_dates_order_check CHECK (deadline > start_date),
          CONSTRAINT goal_baseline_target_check CHECK (baseline = 0 OR baseline < target),
          CONSTRAINT goal_rate_target_check
            CHECK (metric <> 'collection_rate_month' OR target <= 100)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE note (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          owner_id uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
          text text NOT NULL CONSTRAINT note_text_check
            CHECK (char_length(text) BETWEEN 1 AND 2000),
          goal_id uuid REFERENCES goal (id) ON DELETE SET NULL,
          course_id uuid REFERENCES course (id) ON DELETE SET NULL,
          cohort_id uuid REFERENCES cohort (id) ON DELETE SET NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          version integer NOT NULL DEFAULT 1
        )
        """
    )
    op.execute("CREATE INDEX note_owner_idx ON note (owner_id, created_at DESC)")
    for table in ("academy_goal", "goal", "note"):
        op.execute(
            f"CREATE TRIGGER {table}_bump_version BEFORE UPDATE ON {table} "
            "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
        )


def downgrade() -> None:
    op.execute("DROP TABLE note")
    op.execute("DROP TABLE goal")
    op.execute("DROP TABLE academy_goal")
