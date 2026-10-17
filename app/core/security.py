import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

# Argon2 with pwdlib's recommended parameters.
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(password_hash.hash, password)


async def verify_password(password: str, hashed: str) -> bool:
    return await asyncio.to_thread(password_hash.verify, password, hashed)

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)

def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def decode_access_token(access_token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            access_token,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=[get_settings().jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return payload
    except jwt.PyJWTError:
        return None

class AccessToken(NamedTuple):
    token: str
    expires_at: datetime


def generate_access_token(encode_data: dict[str, Any], timedelta_min: int | None = None) -> AccessToken:
    """Return a signed JWT carrying `encode_data`, valid for `timedelta_min` minutes, and its expiry.
    Adds `jti` (a unique token id), `iat` (issued at) and `exp` (expiry) to a copy of
    `encode_data`, overriding any keys of the same name. Values must be JSON-serializable,
    so pass UUIDs as strings.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if timedelta_min is None:
        timedelta_min = settings.jwt_access_token_expire_minutes
    expires_at = now + timedelta(minutes=timedelta_min)
    payload = {
        **encode_data,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return AccessToken(token, expires_at)


class InvalidCredentialsError(Exception):
    """The access token is missing, malformed, expired, or its user no longer exists."""


class AuthenticationCreds(NamedTuple):
    user_id: uuid.UUID
    profile_id: uuid.UUID
    session_id: uuid.UUID


def authenticate_access_token(access_token: str) -> AuthenticationCreds:
    payload = decode_access_token(access_token)
    if payload is None or payload.get("type") != "access":
        raise InvalidCredentialsError()
    try:
        user_id = uuid.UUID(payload["sub"])
        profile_id = uuid.UUID(payload["profile_id"])
        session_id = uuid.UUID(payload["session_id"])
    except (KeyError, TypeError, ValueError):
        raise InvalidCredentialsError() from None

    return AuthenticationCreds(user_id=user_id, profile_id=profile_id, session_id=session_id)
