"""Tests for password hashing and JWT generation."""

import uuid
from datetime import timedelta

import jwt
import pytest

from app.config import get_settings
from app.core.security import generate_token, hash_password, password_hash, verify_password


@pytest.fixture
def encode_data() -> dict:
    return {"sub": str(uuid.uuid4()), "profile_id": str(uuid.uuid4()), "type": "access"}


def _decode(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token, settings.jwt_secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm]
    )


def test_token_carries_all_encode_data(encode_data):
    claims = _decode(generate_token(encode_data, 15))
    assert {k: claims[k] for k in encode_data} == encode_data


def test_encode_data_is_not_modified(encode_data):
    original = dict(encode_data)
    generate_token(encode_data, 15)
    assert encode_data == original


def test_token_expires_after_given_minutes(encode_data):
    claims = _decode(generate_token(encode_data, 15))
    assert timedelta(seconds=claims["exp"] - claims["iat"]) == timedelta(minutes=15)


def test_each_token_gets_a_unique_jti(encode_data):
    assert _decode(generate_token(encode_data, 15))["jti"] != _decode(generate_token(encode_data, 15))["jti"]


def test_encode_data_cannot_override_jti_or_expiry(encode_data):
    claims = _decode(generate_token({**encode_data, "jti": "fixed", "exp": 9999999999}, 15))
    assert claims["jti"] != "fixed"
    assert timedelta(seconds=claims["exp"] - claims["iat"]) == timedelta(minutes=15)


def test_token_signed_with_another_key_is_rejected(encode_data):
    token = generate_token(encode_data, 15)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "not-the-real-secret" * 4, algorithms=[get_settings().jwt_algorithm])


# Password hashing


@pytest.mark.anyio
async def test_hash_password_returns_verifiable_argon2_hash():
    hashed = await hash_password("correct horse battery")
    assert hashed.startswith("$argon2")
    assert password_hash.verify("correct horse battery", hashed)
    assert not password_hash.verify("wrong password", hashed)


@pytest.mark.anyio
async def test_same_password_hashes_differently_each_time():
    assert await hash_password("same") != await hash_password("same")


@pytest.mark.anyio
async def test_verify_password_checks_against_hash():
    hashed = await hash_password("correct horse battery")
    assert await verify_password("correct horse battery", hashed)
    assert not await verify_password("wrong password", hashed)
