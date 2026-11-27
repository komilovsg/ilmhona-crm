"""payment discount

A payment may carry a discount: `discount_percent` (1–100) of the month's price and the amount it
takes off (`discount_amount`, computed by the server from the cohort's price). A month is covered
when its payments plus discounts reach the price; a 100 % discount is a payment of 0. One discount
per enrollment month.
"""

from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE payment
          ADD COLUMN discount_percent smallint,
          ADD COLUMN discount_amount numeric(12, 2) NOT NULL DEFAULT 0,
          DROP CONSTRAINT payment_amount_check,
          ADD CONSTRAINT payment_amount_check CHECK (amount >= 0),
          ADD CONSTRAINT payment_discount_check CHECK (
            (discount_percent IS NULL AND discount_amount = 0)
            OR (discount_percent BETWEEN 1 AND 100 AND discount_amount > 0)
          ),
          ADD CONSTRAINT payment_money_check CHECK (amount > 0 OR discount_amount > 0)
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX payment_month_discount_key ON payment (enrollment_id, month_no) "
        "WHERE discount_percent IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX payment_month_discount_key")
    # payments of 0 (a 100 % discount) stay as they are: the old rule holds for new rows only
    op.execute(
        """
        ALTER TABLE payment
          DROP CONSTRAINT payment_money_check,
          DROP CONSTRAINT payment_discount_check,
          DROP CONSTRAINT payment_amount_check,
          ADD CONSTRAINT payment_amount_check CHECK (amount > 0) NOT VALID,
          DROP COLUMN discount_amount,
          DROP COLUMN discount_percent
        """
    )
