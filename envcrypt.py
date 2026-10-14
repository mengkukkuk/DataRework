"""Reversible encryption for secrets stored in .env (currently DB_PASSWORD).

Fernet with a key embedded in the exes (secret.key, bundled by DataRework.spec).
This keeps the password out of casual view in the external .env; it is
obfuscation, not protection against someone who unpacks the exe.

bcrypt is deliberately not used: it is a one-way hash, so the app could never
recover the password to connect to PostgreSQL.
"""
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:"
KEY_FILE = Path(__file__).resolve().parent / "secret.key"


def ensure_key(path=None):
    """Create the key file if missing and return its bytes.

    The key must stay stable across builds: regenerating it orphans every
    enc: string already pasted into a deployed .env.
    """
    path = Path(path or KEY_FILE)
    if not path.is_file():
        path.write_bytes(Fernet.generate_key())
    return path.read_bytes().strip()


def _fernet(key=None):
    return Fernet(key if key is not None else ensure_key())


def is_encrypted(value):
    return bool(value) and value.startswith(PREFIX)


def encrypt(text, key=None):
    return PREFIX + _fernet(key).encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(value, key=None):
    """Return the plaintext for an enc: value; other values pass through."""
    if not is_encrypted(value):
        return value
    try:
        return _fernet(key).decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("value is not a valid token for this build's key") from exc
