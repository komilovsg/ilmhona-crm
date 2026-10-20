"""room, course, cohort, lesson, student, enrollment (stage 1a)"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        CREATE TABLE room (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          branch_id uuid NOT NULL REFERENCES branch (id),
          name text NOT NULL CONSTRAINT room_name_check CHECK (btrim(name) <> ''),
          capacity integer NOT NULL
            CONSTRAINT room_capacity_check CHECK (capacity BETWEEN 1 AND 100),
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT room_branch_name_key UNIQUE (branch_id, name),
          CONSTRAINT room_id_branch_key UNIQUE (id, branch_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE course (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          name text NOT NULL CONSTRAINT course_name_key UNIQUE
            CONSTRAINT course_name_check CHECK (btrim(name) <> ''),
          direction text,
          default_price_month numeric(12, 2) NOT NULL DEFAULT 0
            CONSTRAINT course_price_check CHECK (default_price_month >= 0),
          duration_months integer NOT NULL
            CONSTRAINT course_duration_check CHECK (duration_months BETWEEN 1 AND 36),
          format text NOT NULL
            CONSTRAINT course_format_check CHECK (format IN ('offline', 'online')),
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE SEQUENCE cohort_code_seq")
    # Dates stay inside 2020..2035 (#8), lesson time 07:00-22:00 and 30-240 min (#6).
    op.execute(
        """
        CREATE TABLE cohort (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          code text NOT NULL CONSTRAINT cohort_code_key UNIQUE
            DEFAULT 'G-' || lpad(nextval('cohort_code_seq')::text, 3, '0'),
          course_id uuid NOT NULL REFERENCES course (id),
          branch_id uuid NOT NULL REFERENCES branch (id),
          instructor_id uuid REFERENCES app_user (id),
          room_id uuid NOT NULL,
          start_date date NOT NULL,
          end_date date NOT NULL,
          weekdays smallint[] NOT NULL,
          start_time time NOT NULL,
          end_time time NOT NULL,
          capacity integer NOT NULL,
          price_month numeric(12, 2) NOT NULL,
          status text NOT NULL DEFAULT 'набор',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT cohort_room_branch_fkey FOREIGN KEY (room_id, branch_id)
            REFERENCES room (id, branch_id),
          CONSTRAINT cohort_dates_order_check CHECK (end_date > start_date),
          CONSTRAINT cohort_dates_range_check CHECK (
            start_date >= DATE '2020-01-01' AND end_date <= DATE '2035-12-31'),
          CONSTRAINT cohort_weekdays_check CHECK (
            cardinality(weekdays) BETWEEN 1 AND 7
            AND weekdays <@ ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[]),
          CONSTRAINT cohort_time_range_check CHECK (
            start_time >= TIME '07:00' AND end_time <= TIME '22:00'),
          CONSTRAINT cohort_duration_check CHECK (
            extract(epoch FROM end_time - start_time) / 60 BETWEEN 30 AND 240),
          CONSTRAINT cohort_capacity_check CHECK (capacity BETWEEN 1 AND 100),
          CONSTRAINT cohort_price_check CHECK (price_month >= 0),
          CONSTRAINT cohort_status_check CHECK (
            status IN ('набор', 'активный', 'завершён', 'отменён'))
        )
        """
    )
    op.execute("CREATE INDEX cohort_branch_idx ON cohort (branch_id)")
    op.execute("CREATE INDEX cohort_instructor_idx ON cohort (instructor_id)")
    op.execute("CREATE INDEX cohort_room_idx ON cohort (room_id)")
    op.execute("CREATE INDEX cohort_course_idx ON cohort (course_id)")
    op.execute("CREATE INDEX cohort_status_idx ON cohort (status)")
    # A lesson lives on one local day (Asia/Dushanbe), inside the same time window as a cohort.
    local_start = "(starts_at AT TIME ZONE 'Asia/Dushanbe')"
    local_end = "(ends_at AT TIME ZONE 'Asia/Dushanbe')"
    op.execute(
        f"""
        CREATE TABLE lesson (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          cohort_id uuid NOT NULL REFERENCES cohort (id) ON DELETE CASCADE,
          room_id uuid NOT NULL REFERENCES room (id),
          lesson_date date NOT NULL,
          starts_at timestamptz NOT NULL,
          ends_at timestamptz NOT NULL,
          cancelled boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT lesson_date_check CHECK (lesson_date = {local_start}::date),
          CONSTRAINT lesson_same_day_check CHECK ({local_start}::date = {local_end}::date),
          CONSTRAINT lesson_dates_range_check CHECK (
            lesson_date BETWEEN DATE '2020-01-01' AND DATE '2035-12-31'),
          CONSTRAINT lesson_time_range_check CHECK (
            {local_start}::time >= TIME '07:00' AND {local_end}::time <= TIME '22:00'),
          CONSTRAINT lesson_duration_check CHECK (
            extract(epoch FROM ends_at - starts_at) / 60 BETWEEN 30 AND 240),
          CONSTRAINT lesson_room_no_overlap EXCLUDE USING gist (
            room_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE (NOT cancelled)
        )
        """
    )
    op.execute("CREATE INDEX lesson_cohort_idx ON lesson (cohort_id, starts_at)")
    op.execute("CREATE INDEX lesson_starts_idx ON lesson (starts_at)")
    op.execute(
        """
        CREATE TABLE student (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          full_name text NOT NULL CONSTRAINT student_name_check CHECK (btrim(full_name) <> ''),
          gender text CONSTRAINT student_gender_check CHECK (gender IN ('male', 'female')),
          phone text,
          branch_id uuid NOT NULL REFERENCES branch (id),
          source_lead_id uuid,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX student_branch_idx ON student (branch_id)")
    op.execute(
        """
        CREATE TABLE enrollment (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          cohort_id uuid NOT NULL REFERENCES cohort (id),
          student_id uuid NOT NULL REFERENCES student (id),
          status text NOT NULL DEFAULT 'активный'
            CONSTRAINT enrollment_status_check CHECK (
              status IN ('активный', 'завершил', 'выпускник', 'отчислен')),
          enrolled_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT enrollment_cohort_student_key UNIQUE (cohort_id, student_id)
        )
        """
    )
    op.execute("CREATE INDEX enrollment_student_idx ON enrollment (student_id)")


def downgrade() -> None:
    for table in ("enrollment", "student", "lesson", "cohort", "course", "room"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP SEQUENCE cohort_code_seq")
