"""Password hashing (argon2id), strength rules, temp passwords, tokens."""

import hashlib
import secrets

import argon2
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.password_policy import generate

_hasher = argon2.PasswordHasher()
_DUMMY = _hasher.hash("timing-equalizer-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    """`stored` None (no such user) costs as much as a real check: timing does not reveal
    which logins exist."""
    try:
        _hasher.verify(stored or _DUMMY, password)
    except VerificationError:
        return False
    except InvalidHashError:
        # an unusable hash (an imported account before activation) costs a real check too
        try:
            _hasher.verify(_DUMMY, password)
        except VerificationError:
            pass
        return False
    return stored is not None


def temp_password(login: str | None = None) -> str:
    return generate(login)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()
