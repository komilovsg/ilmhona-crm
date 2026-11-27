"""cohort code past 999: zero-pad to 3 digits, but never truncate

`lpad(n::text, 3, '0')` cuts a longer string, so cohort 1000 got 'G-100' and collided.
"""

from alembic import op

revision = "0034"
down_revision = "0033"

NEW = (
    "'G-' || CASE WHEN nextval('cohort_code_seq') < 1000 "
    "THEN lpad(currval('cohort_code_seq')::text, 3, '0') ELSE currval('cohort_code_seq')::text END"
)
OLD = "'G-' || lpad(nextval('cohort_code_seq')::text, 3, '0')"


def upgrade() -> None:
    op.execute(f"ALTER TABLE cohort ALTER COLUMN code SET DEFAULT {NEW}")


def downgrade() -> None:
    op.execute(f"ALTER TABLE cohort ALTER COLUMN code SET DEFAULT {OLD}")
