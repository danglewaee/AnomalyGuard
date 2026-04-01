from datetime import datetime, timedelta, timezone
from functools import lru_cache

from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import MissingBackendError

from app.config import settings

_VERIFY_CONTEXT = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")
_FALLBACK_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@lru_cache(maxsize=1)
def _hash_context() -> CryptContext:
    # Prefer bcrypt in real deployments, but fall back to a built-in scheme
    # so local/test environments can still import and exercise the API.
    try:
        _VERIFY_CONTEXT.hash("anomalyguard-backend-check")
    except MissingBackendError:
        return _FALLBACK_CONTEXT
    return _VERIFY_CONTEXT


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _VERIFY_CONTEXT.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return _hash_context().hash(password)


def create_access_token(subject: str, role: str, expires_delta: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta or settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
