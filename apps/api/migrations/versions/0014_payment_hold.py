"""payment_hold: who is entering a payment for an enrollment's month right now (UX only)"""

from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE payment_hold (
          enrollment_id uuid NOT NULL REFERENCES enrollment (id) ON DELETE CASCADE,
          month_no integer NOT NULL CHECK (month_no BETWEEN 1 AND 36),
          user_id uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
          expires_at timestamptz NOT NULL,
          PRIMARY KEY (enrollment_id, month_no)
        )
        """
    )
    op.execute("CREATE INDEX payment_hold_user_idx ON payment_hold (user_id)")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ilm_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON payment_hold TO ilm_app;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE payment_hold")
