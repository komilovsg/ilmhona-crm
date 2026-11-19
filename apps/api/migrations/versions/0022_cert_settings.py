"""certificate settings: the company director shown on every certificate

One row (id = 1): name, title, signature and seal images. Templates draw them through the
`company.director_*` fields and the `{"signature": "director"}` / `{"company": "seal"}` sources,
so changing the director is one edit instead of a new background per template.
"""

from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE cert_settings (
          id smallint PRIMARY KEY DEFAULT 1 CONSTRAINT cert_settings_single_row CHECK (id = 1),
          director_name text NOT NULL DEFAULT ''
            CONSTRAINT cert_settings_name_check CHECK (char_length(director_name) <= 120),
          director_title text NOT NULL DEFAULT 'Директор ОО «Илмхона»'
            CONSTRAINT cert_settings_title_check CHECK (char_length(director_title) <= 120),
          director_signature_asset_id uuid REFERENCES cert_asset (id) ON DELETE SET NULL,
          seal_asset_id uuid REFERENCES cert_asset (id) ON DELETE SET NULL,
          version integer NOT NULL DEFAULT 1,
          updated_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE TRIGGER cert_settings_bump_version BEFORE UPDATE ON cert_settings "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )
    op.execute(
        "INSERT INTO cert_settings (id, director_name, director_title) "
        "VALUES (1, 'Озодамо Фаромуз', 'Директор ОО Илмхона')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE cert_settings")
