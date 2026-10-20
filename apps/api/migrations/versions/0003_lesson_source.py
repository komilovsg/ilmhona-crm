"""lesson.source: generated from the schedule, or added / moved by hand"""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE lesson ADD COLUMN source text NOT NULL DEFAULT 'generated' "
        "CONSTRAINT lesson_source_check CHECK (source IN ('generated', 'manual'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE lesson DROP COLUMN source")
