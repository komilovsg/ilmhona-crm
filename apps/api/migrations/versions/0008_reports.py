"""employment, certificates, manual enrollment status (stage 4)"""

from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    # #13: employment lives here and nowhere else; every other screen reads it from this table.
    op.execute(
        """
        CREATE TABLE employment (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          student_id uuid NOT NULL REFERENCES student (id) ON DELETE CASCADE,
          enrollment_id uuid REFERENCES enrollment (id) ON DELETE SET NULL,
          organization text NOT NULL
            CONSTRAINT employment_organization_check CHECK (length(btrim(organization)) > 0),
          position text,
          employed_at date NOT NULL CONSTRAINT employment_employed_at_check
            CHECK (employed_at BETWEEN DATE '2020-01-01' AND DATE '2035-12-31'),
          created_at timestamptz NOT NULL DEFAULT now(),
          version integer NOT NULL DEFAULT 1
        )
        """
    )
    op.execute("CREATE INDEX employment_student_idx ON employment (student_id)")
    op.execute(
        "CREATE TRIGGER employment_bump_version BEFORE UPDATE ON employment "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )
    # A certificate is for a graduate only: number and date are set together, and a graduate with
    # a certificate cannot change status (the code answers 409 first, the CHECK is the net).
    op.execute("CREATE SEQUENCE certificate_no_seq")
    op.execute(
        """
        ALTER TABLE enrollment
          ADD COLUMN certificate_no text,
          ADD COLUMN certificate_issued_at timestamptz,
          ADD COLUMN status_manual boolean NOT NULL DEFAULT false,
          ADD CONSTRAINT enrollment_certificate_pair_check
            CHECK ((certificate_no IS NULL) = (certificate_issued_at IS NULL)),
          ADD CONSTRAINT enrollment_certificate_graduate_check
            CHECK (certificate_no IS NULL OR status = 'выпускник')
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX enrollment_certificate_no_key ON enrollment (certificate_no) "
        "WHERE certificate_no IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX enrollment_certificate_no_key")
    op.execute(
        "ALTER TABLE enrollment DROP COLUMN certificate_no, DROP COLUMN certificate_issued_at, "
        "DROP COLUMN status_manual"
    )
    op.execute("DROP SEQUENCE certificate_no_seq")
    op.execute("DROP TABLE employment")
