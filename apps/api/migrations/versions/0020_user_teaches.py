"""app_user.teaches: who may be a cohort's instructor, apart from the role"""

from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade() -> None:
    op.execute("ALTER TABLE app_user ADD COLUMN teaches boolean NOT NULL DEFAULT false")
    op.execute(
        "UPDATE app_user SET teaches = true "
        "WHERE role_id IN (SELECT id FROM role WHERE code = 'instructor')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE app_user DROP COLUMN teaches")
