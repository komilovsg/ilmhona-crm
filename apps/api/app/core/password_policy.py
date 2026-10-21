"""The password rules, one source: enforced here, published by `GET /auth/password-policy`,
read by the web (checklist, hints). A new rule: a new id here and in the web `lib/password.ts`.
"""

import re
import secrets

MIN_LENGTH = 10
MAX_LENGTH = 72
_LETTER = re.compile(r"[^\W\d_]")
_DIGIT = re.compile(r"\d")

LENGTH = "length"
LETTER = "letter"
DIGIT = "digit"
NOT_LOGIN = "not_login"
NOT_CURRENT = "not_current"

RULES: list[dict[str, str]] = [
    {"id": LENGTH, "label": f"{MIN_LENGTH}–{MAX_LENGTH} символов"},
    {"id": LETTER, "label": "Хотя бы одна буква"},
    {"id": DIGIT, "label": "Хотя бы одна цифра"},
    {"id": NOT_LOGIN, "label": "Не совпадает с логином"},
    {"id": NOT_CURRENT, "label": "Не совпадает с текущим или временным паролем"},
]


def policy() -> dict[str, object]:
    return {"min_length": MIN_LENGTH, "max_length": MAX_LENGTH, "rules": RULES}


def violations(password: str, *, login: str | None = None, current: str | None = None) -> list[str]:
    """Ids of the broken rules (empty = the password is acceptable)."""
    out: list[str] = []
    if not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        out.append(LENGTH)
    if not _LETTER.search(password):
        out.append(LETTER)
    if not _DIGIT.search(password):
        out.append(DIGIT)
    if login is not None and password.casefold() == login.casefold():
        out.append(NOT_LOGIN)
    if current is not None and password == current:
        out.append(NOT_CURRENT)
    return out


# No 0/O/1/l/I: a temporary password is read from a screen and typed by hand.
_LETTERS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITS = "23456789"
_SPECIALS = "!@#$%*-+="


def generate(login: str | None = None) -> str:
    """A random temporary password that passes the policy."""
    while True:
        chars = (
            [secrets.choice(_LETTERS) for _ in range(7)]
            + [secrets.choice(_DIGITS) for _ in range(3)]
            + [secrets.choice(_SPECIALS) for _ in range(2)]
        )
        secrets.SystemRandom().shuffle(chars)
        password = "".join(chars)
        if not violations(password, login=login):
            return password
