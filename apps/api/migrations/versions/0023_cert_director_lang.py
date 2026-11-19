"""certificate director per language

English and Tajik variants of the director name and title. A template of that language prints
its variant; an empty one falls back to the Russian columns.
"""

from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade() -> None:
    for lang in ("en", "tg"):
        for part in ("name", "title"):
            op.execute(
                f"ALTER TABLE cert_settings ADD COLUMN director_{part}_{lang} text NOT NULL "
                f"DEFAULT '' CONSTRAINT cert_settings_{part}_{lang}_check "
                f"CHECK (char_length(director_{part}_{lang}) <= 120)"
            )
    # the English name is left empty (falls back to the Russian one) until the director fills it in
    op.execute("UPDATE cert_settings SET director_title_en = 'CEO Ilmhona' WHERE id = 1")


def downgrade() -> None:
    for lang in ("en", "tg"):
        for part in ("name", "title"):
            op.execute(f"ALTER TABLE cert_settings DROP COLUMN director_{part}_{lang}")
