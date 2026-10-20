"""branch, role, role_permission, app_user, audit_log, auth tables, seeds"""

from alembic import op

revision = "0001"
down_revision = None

SECTIONS = (
    "dashboard",
    "leads",
    "students",
    "cohorts",
    "attendance",
    "payments",
    "rooms",
    "graduates",
    "master_list",
    "marketing",
    "instructors",
    "users",
    "audit",
)
MANAGER = {
    "dashboard": "view",
    "leads": "change",
    "students": "change",
    "cohorts": "change",
    "attendance": "view",
    "payments": "change",
    "rooms": "change",
    "graduates": "view",
    "master_list": "view",
    "marketing": "view",
}
INSTRUCTOR = {"cohorts": "view", "attendance": "change", "instructors": "view"}


def upgrade() -> None:
    sections = ", ".join(f"'{s}'" for s in SECTIONS)
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute(
        "CREATE TABLE branch "
        "(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL UNIQUE)"
    )
    op.execute(
        """
        CREATE TABLE role (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          name text NOT NULL CONSTRAINT role_name_key UNIQUE CHECK (btrim(name) <> ''),
          code text UNIQUE,
          is_system boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE role_permission (
          role_id uuid NOT NULL REFERENCES role (id) ON DELETE CASCADE,
          section text NOT NULL CHECK (section IN ({sections})),
          level text NOT NULL CHECK (level IN ('view', 'change')),
          PRIMARY KEY (role_id, section)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE app_user (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          login citext NOT NULL CONSTRAINT app_user_login_key UNIQUE
            CHECK (btrim(login::text) <> ''),
          full_name text NOT NULL CHECK (btrim(full_name) <> ''),
          phone text CONSTRAINT app_user_phone_key UNIQUE,
          email text,
          branch_id uuid REFERENCES branch (id),
          role_id uuid NOT NULL REFERENCES role (id),
          is_active boolean NOT NULL DEFAULT true,
          password_hash text NOT NULL,
          must_change_password boolean NOT NULL DEFAULT false,
          temp_password_expires_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX app_user_branch_idx ON app_user (branch_id)")
    op.execute("CREATE INDEX app_user_role_idx ON app_user (role_id)")
    op.execute(
        """
        CREATE TABLE audit_log (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          user_id uuid REFERENCES app_user (id) ON DELETE SET NULL,
          action text NOT NULL,
          entity text NOT NULL,
          entity_id text,
          branch_id uuid REFERENCES branch (id),
          diff jsonb NOT NULL DEFAULT '{}',
          at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX audit_log_at_idx ON audit_log (at DESC, id DESC)")
    op.execute("CREATE INDEX audit_log_entity_idx ON audit_log (entity, entity_id)")
    op.execute("CREATE INDEX audit_log_user_idx ON audit_log (user_id)")
    op.execute(
        """
        CREATE TABLE refresh_token (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
          family_id uuid NOT NULL,
          token_hash bytea NOT NULL UNIQUE,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          revoked_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX refresh_token_user_idx ON refresh_token (user_id)")
    op.execute(
        """
        CREATE TABLE login_attempt (
          login citext PRIMARY KEY,
          failures integer NOT NULL DEFAULT 0,
          locked_until timestamptz
        )
        """
    )

    op.execute("INSERT INTO branch (name) VALUES ('Душанбе'), ('Истаравшан')")
    op.execute(
        "INSERT INTO role (name, code, is_system) VALUES "
        "('Суперадмин', 'superadmin', true), ('Менеджер', 'manager', true), "
        "('Инструктор', 'instructor', true)"
    )
    for code, rights in (
        ("superadmin", {s: "change" for s in SECTIONS}),
        ("manager", MANAGER),
        ("instructor", INSTRUCTOR),
    ):
        for section, level in rights.items():
            op.execute(
                "INSERT INTO role_permission (role_id, section, level) "
                f"SELECT id, '{section}', '{level}' FROM role WHERE code = '{code}'"
            )


def downgrade() -> None:
    for table in (
        "login_attempt",
        "refresh_token",
        "audit_log",
        "app_user",
        "role_permission",
        "role",
        "branch",
    ):
        op.execute(f"DROP TABLE {table}")
