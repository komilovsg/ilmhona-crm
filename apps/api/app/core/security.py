"""Password hashing (argon2id), strength rules, temp passwords, tokens."""

import hashlib
import re
import secrets

import argon2
from argon2.exceptions import InvalidHashError, VerificationError

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72
_LETTER = re.compile(r"[^\W\d_]")
_DIGIT = re.compile(r"\d")
_SPECIAL = re.compile(r"[^\w\s]|_")

_hasher = argon2.PasswordHasher()
_DUMMY = _hasher.hash("timing-equalizer-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    """`stored` None (no such user) costs as much as a real check: timing does not reveal
    which logins exist."""
    try:
        _hasher.verify(stored or _DUMMY, password)
    except VerificationError, InvalidHashError:
        return False
    return stored is not None


def is_strong(password: str) -> bool:
    return (
        PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
        and bool(_LETTER.search(password))
        and bool(_DIGIT.search(password))
        and bool(_SPECIAL.search(password))
    )


# No 0/O/1/l/I: the password is read from a screen and typed by hand.
_LETTERS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITS = "23456789"
_SPECIALS = "!@#$%*-+="


def temp_password() -> str:
    chars = (
        [secrets.choice(_LETTERS) for _ in range(7)]
        + [secrets.choice(_DIGITS) for _ in range(3)]
        + [secrets.choice(_SPECIALS) for _ in range(2)]
    )
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()
