from app.core.errors import VALIDATION_FAILED, errors

# params: months (how many months the cohort runs)
PAYMENT_MONTH_INVALID = errors.define(
    "payment_month_invalid", 422, "Month is outside the months of the cohort"
)
PAYMENT_CONFIRMED = errors.define(
    "payment_confirmed", 409, "A confirmed payment cannot be changed or deleted: unconfirm it"
)
IDEMPOTENCY_KEY_REUSED = errors.define(
    "idempotency_key_reused", 409, "The key was used for a different payment"
)
ENROLLMENT_HAS_PAYMENTS = errors.define(
    "enrollment_has_payments", 409, "The enrollment has payments"
)
COHORT_NO_INSTRUCTOR = errors.define("cohort_no_instructor", 422, "The cohort has no instructor")
PAYOUT_PERIOD_INVALID = errors.define(
    "payout_period_invalid", 422, "The cohort does not run in that month"
)
PAYOUT_EXISTS = errors.define(
    "payout_exists", 409, "The instructor was already paid for that cohort and month"
)

errors.on_constraint("payment_enrollment_fkey", ENROLLMENT_HAS_PAYMENTS)
errors.on_constraint("instructor_payout_key", PAYOUT_EXISTS)
for _check in (
    "payment_month_no_check",
    "payment_amount_check",
    "payment_method_check",
    "payment_paid_at_check",
    "payment_status_check",
    "payment_confirmed_check",
    "payout_period_check",
    "payout_amount_check",
    "payout_paid_at_check",
    "payout_method_check",
    "app_user_default_rate_check",
    "cohort_instructor_rate_check",
):
    errors.on_constraint(_check, VALIDATION_FAILED)
