"""grading schemes: the academy standard, per-cohort overrides, scores per category

`grading_scheme` with `cohort_id` NULL is the academy standard (exactly one); a row with a cohort
is that cohort's own scheme (none = the cohort follows the standard). `grading_category` holds the
ordered categories of a scheme: one `attendance` category (points computed from the attendance
cells) and `manual` ones the teacher fills in. A deferred trigger keeps every scheme at exactly
100 points with exactly one attendance category.

Scores move from `grade.homework` / `grade.final` to `grade_score (enrollment, category_key)`.
A score is keyed by the category key, not by a category row: a category removed from a scheme
leaves its scores in place (archived, named through `grading_key`), and they count again if the
category comes back. `grade` stays as the per-enrollment row whose version guards score edits
(#25).

The standard starts as Посещаемость 20 (auto) · Домашние задания 40 · Финал 40, pass 70, so
every total stays exactly what it was. Downgrade puts homework / final back (capped at 40).
"""

from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE grading_scheme (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          cohort_id uuid UNIQUE REFERENCES cohort (id) ON DELETE CASCADE,
          pass_score smallint NOT NULL DEFAULT 70
            CONSTRAINT grading_scheme_pass_check CHECK (pass_score BETWEEN 0 AND 100),
          target_retention smallint NOT NULL DEFAULT 85
            CONSTRAINT grading_scheme_retention_check CHECK (target_retention BETWEEN 0 AND 100),
          target_attendance smallint NOT NULL DEFAULT 80
            CONSTRAINT grading_scheme_attendance_check CHECK (target_attendance BETWEEN 0 AND 100),
          target_pass_rate smallint NOT NULL DEFAULT 70
            CONSTRAINT grading_scheme_pass_rate_check CHECK (target_pass_rate BETWEEN 0 AND 100),
          updated_at timestamptz NOT NULL DEFAULT now(),
          updated_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          version integer NOT NULL DEFAULT 1
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX grading_scheme_one_standard ON grading_scheme ((true)) "
        "WHERE cohort_id IS NULL"
    )
    op.execute(
        "CREATE TRIGGER grading_scheme_bump_version BEFORE UPDATE ON grading_scheme "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )
    op.execute(
        """
        CREATE TABLE grading_category (
          scheme_id uuid NOT NULL REFERENCES grading_scheme (id) ON DELETE CASCADE,
          key text NOT NULL CONSTRAINT grading_category_key_check
            CHECK (key ~ '^[a-z][a-z0-9_]{0,39}$'),
          name text NOT NULL CONSTRAINT grading_category_name_check
            CHECK (length(btrim(name)) BETWEEN 1 AND 60),
          weight smallint NOT NULL CONSTRAINT grading_category_weight_check
            CHECK (weight BETWEEN 0 AND 100),
          kind text NOT NULL CONSTRAINT grading_category_kind_check
            CHECK (kind IN ('attendance', 'manual')),
          position smallint NOT NULL,
          PRIMARY KEY (scheme_id, key),
          -- the attendance category always has the key `attendance`; a manual one has points
          CONSTRAINT grading_category_attendance_key_check
            CHECK ((kind = 'attendance') = (key = 'attendance')),
          CONSTRAINT grading_category_manual_weight_check CHECK (kind = 'attendance' OR weight >= 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX grading_category_name_key ON grading_category (scheme_id, lower(name))"
    )
    # weights sum to exactly 100, exactly one attendance category: checked at commit, so a
    # scheme can be rewritten row by row inside one transaction
    op.execute(
        """
        CREATE FUNCTION grading_scheme_check() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          sid uuid := COALESCE(NEW.scheme_id, OLD.scheme_id);
          total int;
          att int;
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM grading_scheme WHERE id = sid) THEN
            RETURN NULL;  -- the scheme itself was deleted
          END IF;
          SELECT COALESCE(sum(weight), 0), count(*) FILTER (WHERE kind = 'attendance')
            INTO total, att FROM grading_category WHERE scheme_id = sid;
          IF total <> 100 THEN
            RAISE EXCEPTION 'grading scheme % sums to % points, not 100', sid, total
              USING ERRCODE = 'check_violation', CONSTRAINT = 'grading_scheme_sum_100';
          END IF;
          IF att <> 1 THEN
            RAISE EXCEPTION 'grading scheme % has % attendance categories', sid, att
              USING ERRCODE = 'check_violation', CONSTRAINT = 'grading_scheme_one_attendance';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER grading_category_check AFTER INSERT OR UPDATE OR DELETE "
        "ON grading_category DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION grading_scheme_check()"
    )
    op.execute(
        """
        CREATE TABLE grade_score (
          enrollment_id uuid NOT NULL REFERENCES enrollment (id) ON DELETE CASCADE,
          category_key text NOT NULL,
          points smallint NOT NULL CONSTRAINT grade_score_points_check
            CHECK (points BETWEEN 0 AND 100),
          PRIMARY KEY (enrollment_id, category_key)
        )
        """
    )
    # the last name of every category key ever used: archived scores still read with a name
    op.execute("CREATE TABLE grading_key (key text PRIMARY KEY, name text NOT NULL)")
    op.execute(
        "INSERT INTO grading_key (key, name) VALUES "
        "('attendance', 'Посещаемость'), ('homework', 'Домашние задания'), ('final', 'Финал')"
    )
    # the academy standard: the scale every existing total was computed on
    op.execute(
        """
        WITH s AS (INSERT INTO grading_scheme (cohort_id) VALUES (NULL) RETURNING id)
        INSERT INTO grading_category (scheme_id, key, name, weight, kind, position)
        SELECT s.id, c.key, c.name, c.weight, c.kind, c.position FROM s, (VALUES
          ('attendance', 'Посещаемость', 20, 'attendance', 0),
          ('homework', 'Домашние задания', 40, 'manual', 1),
          ('final', 'Финал', 40, 'manual', 2)) AS c (key, name, weight, kind, position)
        """
    )
    op.execute(
        "INSERT INTO grade_score (enrollment_id, category_key, points) "
        "SELECT enrollment_id, 'homework', homework FROM grade WHERE homework IS NOT NULL "
        "UNION ALL "
        "SELECT enrollment_id, 'final', final FROM grade WHERE final IS NOT NULL"
    )
    op.execute("ALTER TABLE grade DROP COLUMN homework, DROP COLUMN final")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE grade "
        "ADD COLUMN homework smallint CONSTRAINT grade_homework_check "
        "CHECK (homework BETWEEN 0 AND 40), "
        "ADD COLUMN final smallint CONSTRAINT grade_final_check CHECK (final BETWEEN 0 AND 40)"
    )
    for key in ("homework", "final"):
        op.execute(
            f"UPDATE grade g SET {key} = LEAST(s.points, 40) FROM grade_score s "
            f"WHERE s.enrollment_id = g.enrollment_id AND s.category_key = '{key}'"
        )
    op.execute("DROP TABLE grading_key")
    op.execute("DROP TABLE grade_score")
    op.execute("DROP TABLE grading_category")
    op.execute("DROP FUNCTION grading_scheme_check()")
    op.execute("DROP TABLE grading_scheme")
