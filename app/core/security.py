import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

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

def generate_token(encode_data: dict[str, Any], timedelta_min: int | None = None) -> str:
    """Return a signed JWT carrying `encode_data`, valid for `timedelta_min` minutes.
    Adds `jti` (a unique token id), `iat` (issued at) and `exp` (expiry) to a copy of
    `encode_data`, overriding any keys of the same name. Values must be JSON-serializable,
    so pass UUIDs as strings.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if timedelta_min is None:
        timedelta_min = settings.jwt_access_token_expire_minutes
    payload = {
        **encode_data,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=timedelta_min),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )