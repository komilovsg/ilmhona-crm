"""certificate keeps the template version it was drawn from

`enrollment.certificate_version_id` points at the published version a certificate renders with, so
publishing a new version of a template never changes a certificate that is already issued.
Certificates issued so far are pinned to the newest version of the template the rules choose for
them today (the same choice the PDF made until now).
"""

from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE enrollment ADD COLUMN certificate_version_id uuid "
        "REFERENCES cert_template_version (id) ON DELETE SET NULL"
    )
    op.execute(
        """
        UPDATE enrollment e SET certificate_version_id = (
            SELECT v.id FROM cert_template_version v
            WHERE v.template_id = COALESCE(
                (SELECT r.template_id FROM cert_template_rule r
                   JOIN cert_template t ON t.id = r.template_id AND t.status = 'active'
                  WHERE r.course_id = c.course_id AND r.instructor_id = c.instructor_id LIMIT 1),
                (SELECT r.template_id FROM cert_template_rule r
                   JOIN cert_template t ON t.id = r.template_id AND t.status = 'active'
                  WHERE r.course_id = c.course_id AND r.instructor_id IS NULL LIMIT 1),
                (SELECT t.id FROM cert_template t WHERE t.key = 'general_ru')
            )
            ORDER BY v.version_no DESC LIMIT 1
        )
        FROM cohort c
        WHERE c.id = e.cohort_id AND e.certificate_no IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE enrollment DROP COLUMN certificate_version_id")
