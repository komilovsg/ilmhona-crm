"""merged-away accounts stop teaching

`merge-users` used to deactivate the source but leave `teaches = true`, so the same person showed
twice in the instructors list. The source is found by its `user.merge` audit row (entity app_user,
entity_id = the source id); only inactive accounts are touched.
"""

from alembic import op

revision = "0039"
down_revision = "0038"

FIX_SQL = (
    "UPDATE app_user SET teaches = false WHERE teaches AND NOT is_active "
    "AND id::text IN (SELECT entity_id FROM audit_log "
    "WHERE action = 'user.merge' AND entity = 'app_user' AND entity_id IS NOT NULL)"
)


def upgrade() -> None:
    op.execute(FIX_SQL)


def downgrade() -> None:
    """No-op: the previous `teaches` values are not recorded, and the old state was the bug."""
