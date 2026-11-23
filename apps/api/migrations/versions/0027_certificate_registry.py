"""certificate registry: issued certificates, verify settings, section certificates

A row of `certificate` is one issued certificate: the exact template version and a snapshot of
every value it shows, so a later PDF is identical whatever changes in the CRM afterwards. One
`valid` row per enrollment; a reissue marks the old row `replaced`. The number stays
`enrollment.certificate_no`. A non-graduate can be numbered through the settings switch: such an
enrollment carries `certificate_non_graduate`, which the graduate-only check on it allows.
"""

from alembic import op

revision = "0027"
down_revision = "0026"

OLD_SECTIONS = (
    "dashboard", "leads", "students", "cohorts", "attendance", "payments", "rooms", "graduates",
    "master_list", "marketing", "instructors", "users", "audit", "cert_templates",
)  # fmt: skip


def _check(sections: tuple[str, ...]) -> str:
    return "section IN (" + ", ".join(f"'{s}'" for s in sections) + ")"


def upgrade() -> None:
    op.execute("ALTER TABLE role_permission DROP CONSTRAINT role_permission_section_check")
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT role_permission_section_check "
        f"CHECK ({_check((*OLD_SECTIONS, 'certificates'))})"
    )
    op.execute("ALTER TABLE enrollment DROP CONSTRAINT enrollment_certificate_graduate_check")
    op.execute(
        "ALTER TABLE enrollment ADD COLUMN certificate_non_graduate boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE enrollment ADD CONSTRAINT enrollment_certificate_graduate_check "
        "CHECK (certificate_no IS NULL OR status = 'выпускник' OR certificate_non_graduate)"
    )
    op.execute(
        """
        ALTER TABLE cert_settings
          ADD COLUMN verify_base_url text,
          ADD COLUMN allow_non_graduate boolean NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        CREATE TABLE certificate (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          number text NOT NULL,
          verify_code text NOT NULL CONSTRAINT certificate_verify_code_key UNIQUE,
          enrollment_id uuid NOT NULL REFERENCES enrollment (id),
          cohort_id uuid NOT NULL REFERENCES cohort (id),
          course_id uuid NOT NULL REFERENCES course (id),
          branch_id uuid NOT NULL REFERENCES branch (id),
          instructor_id uuid REFERENCES app_user (id) ON DELETE SET NULL,
          template_id uuid NOT NULL REFERENCES cert_template (id),
          template_version_id uuid NOT NULL REFERENCES cert_template_version (id),
          lang text NOT NULL,
          data jsonb NOT NULL,
          status text NOT NULL DEFAULT 'valid' CONSTRAINT certificate_status_check
            CHECK (status IN ('valid', 'replaced', 'revoked')),
          replaced_by_id uuid REFERENCES certificate (id),
          comment text,
          revoke_reason text,
          revoked_at timestamptz,
          revoked_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          issued_at timestamptz NOT NULL DEFAULT now(),
          issued_by uuid REFERENCES app_user (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX certificate_one_valid_key ON certificate (enrollment_id) "
        "WHERE status = 'valid'"
    )
    op.execute("CREATE INDEX certificate_number_idx ON certificate (number)")
    op.execute("CREATE INDEX certificate_cohort_idx ON certificate (cohort_id)")
    op.execute("CREATE INDEX certificate_status_idx ON certificate (status)")


def downgrade() -> None:
    op.execute("DROP TABLE certificate")
    op.execute(
        "ALTER TABLE cert_settings DROP COLUMN allow_non_graduate, DROP COLUMN verify_base_url"
    )
    # the graduate-only rule comes back: a number held by a non-graduate is dropped first
    op.execute(
        "UPDATE enrollment SET certificate_no = NULL, certificate_issued_at = NULL "
        "WHERE certificate_no IS NOT NULL AND status <> 'выпускник'"
    )
    op.execute("ALTER TABLE enrollment DROP CONSTRAINT enrollment_certificate_graduate_check")
    op.execute("ALTER TABLE enrollment DROP COLUMN certificate_non_graduate")
    op.execute(
        "ALTER TABLE enrollment ADD CONSTRAINT enrollment_certificate_graduate_check "
        "CHECK (certificate_no IS NULL OR status = 'выпускник')"
    )
    op.execute("DELETE FROM role_permission WHERE section = 'certificates'")
    op.execute("ALTER TABLE role_permission DROP CONSTRAINT role_permission_section_check")
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT role_permission_section_check "
        f"CHECK ({_check(OLD_SECTIONS)})"
    )
