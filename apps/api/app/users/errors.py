from app.core.errors import CONCURRENT_CHANGE, errors

LOGIN_TAKEN = errors.define("login_taken", 409, "Login already used")
PHONE_TAKEN = errors.define("phone_taken", 409, "Phone already used")
ROLE_NOT_ASSIGNABLE = errors.define(
    "role_not_assignable", 403, "You cannot give or change a role with more rights than yours"
)
BRANCH_FORBIDDEN = errors.define("branch_forbidden", 403, "Outside your branch")
CANNOT_DEACTIVATE_SELF = errors.define(
    "cannot_deactivate_self", 409, "You cannot lock yourself out"
)
LAST_SUPERADMIN = errors.define("last_superadmin", 409, "The last active superadmin stays")
USER_IN_USE = errors.define("user_in_use", 409, "User is referenced; deactivate instead")

errors.on_constraint("app_user_login_key", LOGIN_TAKEN)
errors.on_constraint("app_user_phone_key", PHONE_TAKEN)
# a role or branch deleted while a user is being saved
errors.on_constraint("app_user_role_id_fkey", CONCURRENT_CHANGE)
errors.on_constraint("app_user_branch_id_fkey", CONCURRENT_CHANGE)
