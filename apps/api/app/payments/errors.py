from app.core.errors import VALIDATION_FAILED, errors

# params: months (how many months the cohort runs)
PAYMENT_MONTH_INVALID = errors.define(
    "payment_month_invalid", 422, "Month is outside the months of the cohort"
)
# params of both: month_no, price, paid (entered: pending + confirmed), remaining (price - paid),
# payments [{amount, status, created_by, created_at}] already entered for that month
MONTH_ALREADY_PAID = errors.define("month_already_paid", 409, "The month is already paid in full")
MONTH_OVERPAID = errors.define(
    "month_overpaid", 409, "The amount is more than what is left to pay for the month"
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
# a discount needs a reason: the payment's note (the form's «Заметка»)
DISCOUNT_REASON_REQUIRED = errors.define(
    "discount_reason_required", 422, "A discount needs a reason in the note"
)
DISCOUNT_NO_PRICE = errors.define(
    "discount_no_price", 422, "The cohort has no price: nothing to take a discount from"
)
# params: month_no, percent (the discount already given for that month)
MONTH_DISCOUNT_EXISTS = errors.define(
    "month_discount_exists", 409, "The month already has a discount"
)
PAYMENT_AMOUNT_ZERO = errors.define(
    "payment_amount_zero", 422, "A payment of 0 is only a 100 % discount"
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
errors.on_constraint("payment_month_discount_key", MONTH_DISCOUNT_EXISTS)
for _check in (
    "payment_month_no_check",
    "payment_amount_check",
    "payment_discount_check",
    "payment_money_check",
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
