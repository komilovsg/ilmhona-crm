from app.core.errors import VALIDATION_FAILED, errors

NOT_GRADUATE = errors.define("not_graduate", 409, "Only a graduate has a certificate or a job")
CERTIFICATE_ISSUED = errors.define(
    "certificate_issued", 409, "The certificate is already issued: the status stays «выпускник»"
)
EMPLOYMENT_ENROLLMENT_MISMATCH = errors.define(
    "employment_enrollment_mismatch", 422, "The enrollment belongs to another student"
)

errors.on_constraint("enrollment_certificate_graduate_check", CERTIFICATE_ISSUED)
for _check in ("employment_organization_check", "employment_employed_at_check"):
    errors.on_constraint(_check, VALIDATION_FAILED)
