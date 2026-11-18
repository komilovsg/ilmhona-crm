"""certificate templates: assets, templates, versions, rules; section cert_templates

Templates are data (a JSON layout plus a background image), rendered to PDF by the API. A
published version is never updated: a change is a new version row.
"""

from alembic import op

revision = "0020"
down_revision = "0019"

OLD_SECTIONS = (
    "dashboard", "leads", "students", "cohorts", "attendance", "payments", "rooms", "graduates",
    "master_list", "marketing", "instructors", "users", "audit",
)  # fmt: skip


def _check(sections: tuple[str, ...]) -> str:
    return "section IN (" + ", ".join(f"'{s}'" for s in sections) + ")"


def upgrade() -> None:
    op.execute("ALTER TABLE role_permission DROP CONSTRAINT role_permission_section_check")
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT role_permission_section_check "
        f"CHECK ({_check((*OLD_SECTIONS, 'cert_templates'))})"
    )
    op.execute(
        """
        CREATE TABLE cert_asset (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          kind text NOT NULL CONSTRAINT cert_asset_kind_check
            CHECK (kind IN ('background', 'signature', 'seal', 'logo', 'image')),
          mime text NOT NULL CONSTRAINT cert_asset_mime_check
            CHECK (mime IN ('image/png', 'image/jpeg', 'image/svg+xml')),
          data bytea NOT NULL,
          sha256 text NOT NULL CONSTRAINT cert_asset_sha256_key UNIQUE,
          size_bytes integer NOT NULL CONSTRAINT cert_asset_size_check
            CHECK (size_bytes <= 5242880),
          width_px integer,
          height_px integer,
          uploaded_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE cert_template (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          key text NOT NULL CONSTRAINT cert_template_key_key UNIQUE
            CHECK (key ~ '^[a-z0-9_-]{1,60}$'),
          name text NOT NULL CONSTRAINT cert_template_name_key UNIQUE
            CHECK (btrim(name) <> ''),
          status text NOT NULL DEFAULT 'active' CONSTRAINT cert_template_status_check
            CHECK (status IN ('active', 'archived')),
          lang text NOT NULL DEFAULT 'ru' CONSTRAINT cert_template_lang_check
            CHECK (lang IN ('ru', 'en', 'tg')),
          draft jsonb NOT NULL CONSTRAINT cert_template_draft_check
            CHECK (jsonb_typeof(draft) = 'object' AND pg_column_size(draft) <= 204800),
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          updated_by uuid REFERENCES app_user (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE TRIGGER cert_template_bump_version BEFORE UPDATE ON cert_template "
        "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
    )
    op.execute(
        """
        CREATE TABLE cert_template_version (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          template_id uuid NOT NULL REFERENCES cert_template (id) ON DELETE CASCADE,
          version_no integer NOT NULL CHECK (version_no > 0),
          layout jsonb NOT NULL CONSTRAINT cert_template_version_layout_check
            CHECK (jsonb_typeof(layout) = 'object' AND pg_column_size(layout) <= 204800),
          published_by uuid REFERENCES app_user (id) ON DELETE SET NULL,
          published_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT cert_template_version_no_key UNIQUE (template_id, version_no)
        )
        """
    )
    # a published version is immutable
    op.execute(
        """
        CREATE FUNCTION cert_version_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'cert_template_version rows are never updated';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER cert_template_version_immutable BEFORE UPDATE ON cert_template_version "
        "FOR EACH ROW EXECUTE FUNCTION cert_version_immutable()"
    )
    op.execute(
        """
        CREATE TABLE cert_template_rule (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          course_id uuid NOT NULL REFERENCES course (id) ON DELETE CASCADE,
          instructor_id uuid REFERENCES app_user (id) ON DELETE CASCADE,
          template_id uuid NOT NULL REFERENCES cert_template (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX cert_template_rule_target_key ON cert_template_rule "
        "(course_id, coalesce(instructor_id, '00000000-0000-0000-0000-000000000000'::uuid))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE cert_template_rule")
    op.execute("DROP TABLE cert_template_version")
    op.execute("DROP FUNCTION cert_version_immutable()")
    op.execute("DROP TABLE cert_template")
    op.execute("DROP TABLE cert_asset")
    op.execute("DELETE FROM role_permission WHERE section = 'cert_templates'")
    op.execute("ALTER TABLE role_permission DROP CONSTRAINT role_permission_section_check")
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT role_permission_section_check "
        f"CHECK ({_check(OLD_SECTIONS)})"
    )
