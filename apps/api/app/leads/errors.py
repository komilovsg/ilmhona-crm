from app.core.errors import VALIDATION_FAILED, errors

LEAD_CONVERTED = errors.define(
    "lead_converted", 409, "The lead is already a student: its status stays «записан»"
)
LEAD_USE_CONVERT = errors.define(
    "lead_use_convert", 422, "«записан» is set by converting the lead into a student"
)
CAMPAIGN_BRANCH_MISMATCH = errors.define(
    "campaign_branch_mismatch", 422, "The campaign belongs to another branch than the lead"
)
CAMPAIGN_IN_USE = errors.define("campaign_in_use", 409, "The campaign has leads")
CAMPAIGN_DATES_INVALID = errors.define(
    "campaign_dates_invalid", 422, "The end date is before the start date"
)
# params: limit (bytes or rows)
IMPORT_TOO_LARGE = errors.define("import_too_large", 413, "The file is too large")
IMPORT_TOO_MANY_ROWS = errors.define("import_too_many_rows", 422, "Too many rows in the file")
IMPORT_UNREADABLE = errors.define("import_unreadable", 422, "The file is not a readable CSV")
IMPORT_NO_ROWS = errors.define("import_no_rows", 422, "The file has no rows to import")
IMPORT_MAPPING_INVALID = errors.define(
    "import_mapping_invalid", 422, "Pick the column with the name or the phone"
)

errors.on_constraint("lead_campaign_fkey", CAMPAIGN_IN_USE)
for _check in (
    "lead_name_check",
    "lead_source_check",
    "lead_call_status_check",
    "lead_status_check",
    "campaign_name_check",
    "campaign_platform_check",
    "campaign_start_range_check",
    "campaign_budget_check",
    "campaign_status_check",
    "campaign_end_range_check",
):
    errors.on_constraint(_check, VALIDATION_FAILED)
errors.on_constraint("campaign_dates_order_check", CAMPAIGN_DATES_INVALID)
