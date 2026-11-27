"""donors and cohort funding

`donor` is the list of organisations that pay for students (name, note, archived). A cohort has a
`funding`: платный (as before), бесплатный (price 0, no donor), донор (every student is paid for
by one of the cohort's donors) or смешанный (each student either pays or is paid for by a donor).
`cohort_donor` holds the donors of a cohort; `enrollment.donor_id` the donor of a student, which
must be one of the cohort's donors (composite FK). A donor-funded enrollment owes nothing.
`enrollment.pays_from`: when the student switched from a donor to paying themself; the debt
counts from that month. Old cohorts become «платный», those with a price of 0 «бесплатный».
Section `donors` in the rights matrix; the seeded manager role views it (list and report) by
default, the superadmin has every section anyway.
"""

from alembic import op

revision = "0031"
down_revision = "0029"

OLD_SECTIONS = (
    "dashboard", "leads", "students", "cohorts", "attendance", "payments", "rooms", "graduates",
    "master_list", "marketing", "instructors", "users", "audit", "cert_templates", "certificates",
)  # fmt: skip


def _check(sections: tuple[str, ...]) -> str:
    return "section IN (" + ", ".join(f"'{s}'" for s in sections) + ")"


def upgrade() -> None:
    op.execute("ALTER TABLE role_permission DROP CONSTRAINT role_permission_section_check")
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT role_permission_section_check "
        f"CHECK ({_check((*OLD_SECTIONS, 'donors'))})"
    )
    op.execute(
        "INSERT INTO role_permission (role_id, section, level) "
        "SELECT id, 'donors', 'view' FROM role WHERE code = 'manager'"
    )
    op.execute(
        """
        CREATE TABLE donor (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          name text NOT NULL CONSTRAINT donor_name_key UNIQUE
            CONSTRAINT donor_name_check CHECK (length(btrim(name)) BETWEEN 1 AND 200),
          note text CONSTRAINT donor_note_check CHECK (length(note) <= 1000),
          archived boolean NOT NULL DEFAULT false,
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE TRIGGER donor_bump_version BEFORE UPDATE ON donor "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )
    op.execute(
        """
        ALTER TABLE cohort
          ADD COLUMN funding text NOT NULL DEFAULT 'платный'
            CONSTRAINT cohort_funding_check
            CHECK (funding IN ('платный', 'бесплатный', 'донор', 'смешанный'))
        """
    )
    op.execute("UPDATE cohort SET funding = 'бесплатный' WHERE price_month = 0")
    op.execute(
        "ALTER TABLE cohort ADD CONSTRAINT cohort_free_price_check "
        "CHECK (funding <> 'бесплатный' OR price_month = 0)"
    )
    op.execute(
        """
        CREATE TABLE cohort_donor (
          cohort_id uuid NOT NULL REFERENCES cohort (id) ON DELETE CASCADE,
          donor_id uuid NOT NULL REFERENCES donor (id),
          PRIMARY KEY (cohort_id, donor_id)
        )
        """
    )
    op.execute("CREATE INDEX cohort_donor_donor_idx ON cohort_donor (donor_id)")
    op.execute(
        """
        ALTER TABLE enrollment
          ADD COLUMN donor_id uuid,
          ADD COLUMN pays_from timestamptz,
          ADD CONSTRAINT enrollment_cohort_donor_fkey FOREIGN KEY (cohort_id, donor_id)
            REFERENCES cohort_donor (cohort_id, donor_id)
        """
    )
    op.execute(
        "CREATE INDEX enrollment_donor_idx ON enrollment (donor_id) WHERE donor_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX enrollment_donor_idx")
    op.execute(
        """
        ALTER TABLE enrollment
          DROP CONSTRAINT enrollment_cohort_donor_fkey,
          DROP COLUMN pays_from,
          DROP COLUMN donor_id
        """
    )
    op.execute("DROP TABLE cohort_donor")
    op.execute("ALTER TABLE cohort DROP CONSTRAINT cohort_free_price_check, DROP COLUMN funding")
    op.execute("DROP TABLE donor")
    op.execute("DELETE FROM role_permission WHERE section = 'donors'")
    op.execute("ALTER TABLE role_permission DROP CONSTRAINT role_permission_section_check")
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT role_permission_section_check "
        f"CHECK ({_check(OLD_SECTIONS)})"
    )
