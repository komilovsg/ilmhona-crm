from app.core.errors import errors

# The same answer for an unknown login, a wrong password and a deactivated account.
INVALID_CREDENTIALS = errors.define("invalid_credentials", 401, "Wrong login or password")
TOO_MANY_ATTEMPTS = errors.define("too_many_attempts", 429, "Too many failed logins")
TEMP_PASSWORD_EXPIRED = errors.define(
    "temp_password_expired", 401, "Temporary password expired; ask for a new one"
)
PASSWORD_CHANGE_REQUIRED = errors.define(
    "password_change_required", 403, "Change the temporary password first"
)
WRONG_PASSWORD = errors.define("wrong_password", 400, "Current password is wrong")
WEAK_PASSWORD = errors.define("weak_password", 422, "Password does not meet the rules")
SAME_PASSWORD = errors.define("same_password", 422, "New password equals the current one")
