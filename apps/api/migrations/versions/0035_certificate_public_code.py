"""certificate public code: the code of the public check page `/v/<code>`

Set on issue and reissue from now on; certificates issued before stay without one and are not
checked publicly (their QR keeps pointing where it did). Random, never derived from the number.
"""

from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade() -> None:
    op.execute("ALTER TABLE certificate ADD COLUMN public_code text")
    op.execute(
        "CREATE UNIQUE INDEX certificate_public_code_key ON certificate (public_code) "
        "WHERE public_code IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX certificate_public_code_key")
    op.execute("ALTER TABLE certificate DROP COLUMN public_code")
