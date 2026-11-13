from app.core.errors import errors

# params: problems (Russian sentences, one per problem)
GRADING_SCHEME_INVALID = errors.define(
    "grading_scheme_invalid", 422, "Weights must sum to 100 with one attendance category"
)
# params: categories [{name, scores}]: the removed categories that have entered scores
GRADING_SCORES_ARCHIVED = errors.define(
    "grading_scores_archived", 409, "Removing categories with scores needs a confirmation"
)
COHORT_NOT_COMPLETED = errors.define("cohort_not_completed", 409, "The cohort is not finished")

errors.on_constraint("grading_scheme_sum_100", GRADING_SCHEME_INVALID)
errors.on_constraint("grading_scheme_one_attendance", GRADING_SCHEME_INVALID)
errors.on_constraint("grading_category_name_key", GRADING_SCHEME_INVALID)
errors.on_constraint("grading_category_manual_weight_check", GRADING_SCHEME_INVALID)
