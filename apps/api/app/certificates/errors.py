from app.core.errors import errors

CERT_FIELD_UNKNOWN = errors.define("cert_field_unknown", 422, "Unknown field in the template")
CERT_LAYOUT_INVALID = errors.define("cert_layout_invalid", 422, "The template layout is invalid")
CERT_ASSET_INVALID = errors.define("cert_asset_invalid", 422, "The image is not acceptable")
CERT_ASSET_MISSING = errors.define("cert_asset_missing", 409, "An image of the template is gone")
CERT_GENDER_MISSING = errors.define(
    "cert_gender_missing", 409, "The student's gender is needed by the template"
)
CERT_TEXT_OVERFLOW = errors.define("cert_text_overflow", 409, "The text does not fit its box")
CERT_RENDER_TIMEOUT = errors.define("cert_render_timeout", 503, "Rendering took too long")
CERT_PDF_TOO_LARGE = errors.define("cert_pdf_too_large", 409, "The certificate file is too big")
CERT_NOT_ISSUED = errors.define("cert_not_issued", 409, "The certificate number is not issued yet")
CERT_NO_TEMPLATE = errors.define("cert_no_template", 409, "No published certificate template")
