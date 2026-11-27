"""manager gets `cert_templates` = change by default

Owner decision: superadmin and manager manage certificate templates. Only a manager role without a
`cert_templates` entry is touched, so a later edit by the superadmin stays.
"""

from alembic import op

revision = "0038"
down_revision = "0037"


def upgrade() -> None:
    op.execute(
        "INSERT INTO role_permission (role_id, section, level) "
        "SELECT id, 'cert_templates', 'change' FROM role WHERE code = 'manager' "
        "AND NOT EXISTS (SELECT 1 FROM role_permission rp "
        "WHERE rp.role_id = role.id AND rp.section = 'cert_templates')"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE section = 'cert_templates' AND level = 'change' "
        "AND role_id = (SELECT id FROM role WHERE code = 'manager')"
    )
