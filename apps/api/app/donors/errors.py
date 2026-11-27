from app.core.errors import VALIDATION_FAILED, errors

DONOR_NAME_TAKEN = errors.define("donor_name_taken", 409, "Donor name already used")
# a cohort «донор» needs at least one donor, «смешанный» any number; «платный» / «бесплатный» none
FUNDING_DONORS_INVALID = errors.define(
    "funding_donors_invalid", 422, "The donors do not fit the cohort's funding"
)
DONOR_ARCHIVED = errors.define("donor_archived", 422, "An archived donor cannot be chosen")
# the donor is not one of the cohort's donors (or the cohort takes no donors)
DONOR_NOT_IN_COHORT = errors.define(
    "donor_not_in_cohort", 422, "The donor does not fund this cohort"
)
# a «донор» cohort with more than one donor: the donor of the student must be chosen
DONOR_REQUIRED = errors.define("donor_required", 422, "Choose the donor of the student")
# params: count (students of the cohort that the donor pays for)
DONOR_IN_USE = errors.define("donor_in_use", 409, "Students of the cohort are funded by this donor")
# params: count (students who pay themselves; a «донор» cohort with several donors)
FUNDING_HAS_PAYERS = errors.define(
    "funding_has_payers", 409, "Students of the cohort pay themselves: choose their donors first"
)
PAYMENT_DONOR_FUNDED = errors.define(
    "payment_donor_funded", 409, "The student is funded by a donor: no payments are taken"
)

errors.on_constraint("donor_name_key", DONOR_NAME_TAKEN)
errors.on_constraint("enrollment_cohort_donor_fkey", DONOR_IN_USE)
for _check in ("donor_name_check", "donor_note_check", "cohort_funding_check"):
    errors.on_constraint(_check, VALIDATION_FAILED)
errors.on_constraint("cohort_free_price_check", FUNDING_DONORS_INVALID)
