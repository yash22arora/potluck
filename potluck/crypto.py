"""Encryption for secrets at rest.

A Swiggy access token is, for five days, the ability to spend this household's
money. It does not sit in the database in plaintext.

The key is derived from SECRET_KEY rather than being one, so you can use any
random string instead of having to produce a valid Fernet key by hand.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from potluck.config import get_settings


class SecretKeyMissing(RuntimeError):
    """Raised when something needs to encrypt but SECRET_KEY is unset."""


@lru_cache
def _cipher() -> Fernet:
    secret = get_settings().secret_key
    if not secret:
        raise SecretKeyMissing(
            "SECRET_KEY is not set in this process.\n"
            "  If it is already in your .env, the app started before you added it — "
            "settings are read once at boot, so restart:  make down && make up\n"
            "  If it is genuinely missing:  make env"
        )
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        # Almost always means SECRET_KEY changed since the value was written.
        raise SecretKeyMissing(
            "Could not decrypt a stored secret — has SECRET_KEY changed? "
            "If so, re-run the Swiggy authorization to store fresh tokens."
        ) from exc
