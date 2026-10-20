"""leads and campaigns (stage 3)"""

from alembic import op

revision = "0007"
down_revision = "0006"

SOURCES = (
    "'Facebook', 'Instagram', 'TikTok', 'Telegram', 'сайт', 'рекомендация', 'звонок', 'другое'"
)
PLATFORMS = "'Facebook Ads', 'Instagram', 'TikTok', 'Telegram', 'Google', 'офлайн', 'другое'"


def upgrade() -> None:
    # Ids are generated here (#14), never typed by hand. A campaign with leads cannot be deleted.
    op.execute(
        f"""
        CREATE TABLE campaign (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          name text NOT NULL CONSTRAINT campaign_name_check CHECK (length(btrim(name)) > 0),
          course_id uuid REFERENCES course (id),
          branch_id uuid NOT NULL REFERENCES branch (id),
          platform text NOT NULL
            CONSTRAINT campaign_platform_check CHECK (platform IN ({PLATFORMS})),
          start_date date NOT NULL CONSTRAINT campaign_start_range_check
            CHECK (start_date BETWEEN DATE '2020-01-01' AND DATE '2035-12-31'),
          end_date date,
          budget numeric(12, 2) NOT NULL DEFAULT 0
            CONSTRAINT campaign_budget_check CHECK (budget >= 0),
          status text NOT NULL DEFAULT 'запланирована' CONSTRAINT campaign_status_check
            CHECK (status IN ('запланирована', 'активна', 'остановлена', 'завершена')),
          created_at timestamptz NOT NULL DEFAULT now(),
          version integer NOT NULL DEFAULT 1,
          CONSTRAINT campaign_dates_order_check CHECK (end_date IS NULL OR end_date >= start_date),
          CONSTRAINT campaign_end_range_check
            CHECK (end_date IS NULL OR end_date <= DATE '2035-12-31')
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE lead (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          full_name text NOT NULL CONSTRAINT lead_name_check CHECK (length(btrim(full_name)) > 0),
          raw_name text,
          phone text,
          phone_raw text,
          course_id uuid REFERENCES course (id),
          source text NOT NULL DEFAULT 'другое'
            CONSTRAINT lead_source_check CHECK (source IN ({SOURCES})),
          campaign_id uuid CONSTRAINT lead_campaign_fkey
            REFERENCES campaign (id) ON DELETE RESTRICT,
          branch_id uuid NOT NULL REFERENCES branch (id),
          call_status text NOT NULL DEFAULT 'не звонили' CONSTRAINT lead_call_status_check
            CHECK (call_status IN ('не звонили', 'не ответил', 'позвонили', 'перезвонить')),
          next_contact_at timestamptz,
          status text NOT NULL DEFAULT 'новый' CONSTRAINT lead_status_check
            CHECK (status IN ('новый', 'заинтересован', 'нулевой урок', 'записан', 'отказ')),
          refusal_reason text,
          comment text,
          needs_review boolean NOT NULL DEFAULT false,
          converted_student_id uuid REFERENCES student (id) ON DELETE SET NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          version integer NOT NULL DEFAULT 1
        )
        """
    )
    # the last 9 digits of a phone: how leads and students are matched whatever the formatting
    op.execute(
        r"""
        CREATE FUNCTION phone_key(p text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
          SELECT CASE WHEN length(regexp_replace(p, '\D', '', 'g')) >= 9
                 THEN right(regexp_replace(p, '\D', '', 'g'), 9) END
        $$
        """
    )
    op.execute("CREATE INDEX lead_phone_key_idx ON lead (phone_key(phone))")
    op.execute("CREATE INDEX student_phone_key_idx ON student (phone_key(phone))")
    op.execute("CREATE INDEX lead_created_idx ON lead (created_at)")
    op.execute("CREATE INDEX lead_campaign_idx ON lead (campaign_id)")
    op.execute("CREATE INDEX lead_branch_status_idx ON lead (branch_id, status)")
    op.execute(
        "ALTER TABLE student ADD CONSTRAINT student_source_lead_fkey "
        "FOREIGN KEY (source_lead_id) REFERENCES lead (id) ON DELETE SET NULL"
    )
    for table in ("campaign", "lead"):
        op.execute(
            f"CREATE TRIGGER {table}_bump_version BEFORE UPDATE ON {table} "
            "FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION bump_version()"
        )


def downgrade() -> None:
    op.execute("ALTER TABLE student DROP CONSTRAINT student_source_lead_fkey")
    op.execute("DROP INDEX student_phone_key_idx")
    op.execute("DROP TABLE lead")
    op.execute("DROP FUNCTION phone_key(text)")
    op.execute("DROP TABLE campaign")
