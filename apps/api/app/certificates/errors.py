from app.core.errors import errors

CERT_FIELD_UNKNOWN = errors.define("cert_field_unknown", 422, "Unknown field in the template")
CERT_LAYOUT_INVALID = errors.define("cert_layout_invalid", 422, "The template layout is invalid")
CERT_ASSET_INVALID = errors.define("cert_asset_invalid", 422, "The image is not acceptable")
CERT_ASSET_DIMENSIONS = errors.define("cert_asset_dimensions", 422, "The image is too large")
CERT_ASSET_MISSING = errors.define("cert_asset_missing", 422, "An image of the template is gone")
CERT_GENDER_MISSING = errors.define(
    "cert_gender_missing", 409, "The student's gender is needed by the template"
)
CERT_TEXT_OVERFLOW = errors.define("cert_text_overflow", 409, "The text does not fit its box")
CERT_RENDER_TIMEOUT = errors.define("cert_render_timeout", 503, "Rendering took too long")
CERT_PDF_TOO_LARGE = errors.define("cert_pdf_too_large", 409, "The certificate file is too big")
CERT_NOT_ISSUED = errors.define("cert_not_issued", 409, "The certificate number is not issued yet")
CERT_NO_TEMPLATE = errors.define("cert_no_template", 409, "No published certificate template")
CERT_TEMPLATE_NAME_TAKEN = errors.define(
    "cert_template_name_taken", 409, "A template with this name exists"
)
CERT_NOTHING_TO_PUBLISH = errors.define(
    "cert_nothing_to_publish", 409, "The draft equals the published version"
)
CERT_RULE_DUPLICATE = errors.define(
    "cert_rule_duplicate", 409, "Two rules name the same course and instructor"
)
CERT_RULE_INVALID = errors.define(
    "cert_rule_invalid", 422, "A rule names a missing or archived item"
)
errors.on_constraint("cert_template_name_key", CERT_TEMPLATE_NAME_TAKEN)
errors.on_constraint("cert_template_rule_target_key", CERT_RULE_DUPLICATE)

CERT_ALREADY_ISSUED = errors.define(
    "cert_already_issued", 409, "A valid certificate already exists for the enrollment"
)
CERT_NOT_READY = errors.define("cert_not_ready", 422, "Some enrollments cannot be certified yet")
CERT_NOT_VALID = errors.define("cert_not_valid", 409, "Only a valid certificate can be changed")
CERT_COMMENT_REQUIRED = errors.define("cert_comment_required", 422, "A comment is required")
CERT_CUSTOM_INVALID = errors.define("cert_custom_invalid", 422, "A custom value is not acceptable")
CERT_DIRECTOR_OVERFLOW = errors.define(
    "cert_director_overflow", 422, "The director's name or title does not fit a template"
)
CERT_BATCH_FIXED = errors.define(
    "cert_batch_fixed", 409, "A certificate from an Excel list cannot be reissued"
)
CERT_BULK_FILE = errors.define("cert_bulk_file", 422, "The Excel list is not acceptable")
CERT_BULK_EMPTY = errors.define("cert_bulk_empty", 409, "No row of the list can be issued")
CERT_BRANCH_REQUIRED = errors.define("cert_branch_required", 422, "Choose the branch")
COHORT_NOT_FINISHED = errors.define(
    "cohort_not_finished", 409, "Certificates are issued only for a finished cohort"
)
