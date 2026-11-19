"""instructor signature for certificates

A transparent signature image per instructor; `{"signature": "instructor"}` in a certificate
template draws the signature of the graduate's cohort instructor.
"""

from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app_user ADD COLUMN signature_asset_id uuid "
        "REFERENCES cert_asset (id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE app_user DROP COLUMN signature_asset_id")
