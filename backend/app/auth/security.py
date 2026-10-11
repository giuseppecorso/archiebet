"""Password e token di sessione."""

import hashlib
import secrets

from pwdlib import PasswordHash

MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHash.recommended()  # Argon2id
# Hash di riserva: se l'utente non esiste si verifica comunque una password,
# così i tempi di risposta non rivelano quali nomi utente esistono
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
