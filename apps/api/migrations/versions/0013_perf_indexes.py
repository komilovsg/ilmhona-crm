"""indexes for the hot filters, sorts and joins found by the load measurements"""

from alembic import op

revision = "0013"
down_revision = "0012"

INDEXES = (
    # every authenticated request: «is this session (token family) still live?»
    "refresh_token_family_idx ON refresh_token (family_id, user_id) WHERE revoked_at IS NULL",
    # the audit list: newest first, narrowed by branch / action / entity
    "audit_log_branch_at_idx ON audit_log (branch_id, at DESC, id DESC)",
    "audit_log_action_at_idx ON audit_log (action, at DESC, id DESC)",
    "audit_log_entity_at_idx ON audit_log (entity, at DESC, id DESC)",
    # «today's lessons» (/me/today, dashboard)
    "lesson_date_idx ON lesson (lesson_date)",
    # income by month / payment list totals: confirmed payments in a date range
    "payment_status_paid_idx ON payment (status, paid_at)",
    # graduates and the dashboard graduate count: enrollments of one status, joined to cohorts
    "enrollment_status_idx ON enrollment (status, cohort_id)",
    # leads: course filter, the callback list, the FK of a converted student
    "lead_course_idx ON lead (course_id)",
    "lead_callback_idx ON lead (next_contact_at) WHERE next_contact_at IS NOT NULL",
    "lead_converted_student_idx ON lead (converted_student_id) "
    "WHERE converted_student_id IS NOT NULL",
    # payroll by month, ads by branch and start date
    "payout_paid_at_idx ON instructor_payout (paid_at)",
    "campaign_branch_start_idx ON campaign (branch_id, start_date)",
    # master list order (newest start first); student list order
    "cohort_start_idx ON cohort (start_date DESC)",
    "student_name_idx ON student (full_name, id)",
)


def upgrade() -> None:
    for index in INDEXES:
        op.execute(f"CREATE INDEX {index}")


def downgrade() -> None:
    for index in INDEXES:
        op.execute(f"DROP INDEX {index.split()[0]}")
