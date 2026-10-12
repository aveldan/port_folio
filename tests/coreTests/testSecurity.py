"""Tests for password hashing and JWT generation."""

import uuid
from datetime import timedelta

import jwt
import pytest

from app.config import get_settings
from app.core.security import (
    InvalidCredentialsError,
    authenticate_access_token,
    decode_access_token,
    generate_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_hash,
    verify_password,
)


@pytest.fixture
def encode_data() -> dict:
    return {"sub": str(uuid.uuid4()), "profile_id": str(uuid.uuid4()), "type": "access"}


def _decode(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token, settings.jwt_secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm]
    )


def test_token_carries_all_encode_data(encode_data):
    claims = _decode(generate_access_token(encode_data, 15).token)
    assert {k: claims[k] for k in encode_data} == encode_data


def test_expires_at_matches_exp_claim(encode_data):
    access = generate_access_token(encode_data, 15)
    assert access.expires_at.timestamp() == _decode(access.token)["exp"]


def test_encode_data_is_not_modified(encode_data):
    original = dict(encode_data)
    generate_access_token(encode_data, 15)
    assert encode_data == original


def test_token_expires_after_given_minutes(encode_data):
    claims = _decode(generate_access_token(encode_data, 15).token)
    assert timedelta(seconds=claims["exp"] - claims["iat"]) == timedelta(minutes=15)


def test_each_token_gets_a_unique_jti(encode_data):
    assert _decode(generate_access_token(encode_data, 15).token)["jti"] != _decode(generate_access_token(encode_data, 15).token)["jti"]


def test_encode_data_cannot_override_jti_or_expiry(encode_data):
    claims = _decode(generate_access_token({**encode_data, "jti": "fixed", "exp": 9999999999}, 15).token)
    assert claims["jti"] != "fixed"
    assert timedelta(seconds=claims["exp"] - claims["iat"]) == timedelta(minutes=15)


def test_token_signed_with_another_key_is_rejected(encode_data):
    token = generate_access_token(encode_data, 15).token
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


# Refresh tokens


def test_refresh_tokens_are_random_and_url_safe():
    tokens = {generate_refresh_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(t) >= 43 and "/" not in t and "+" not in t for t in tokens)


def test_refresh_token_hash_is_stable_sha256():
    token = generate_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64
    assert hash_refresh_token(token) != token


# Decoding access tokens


def test_decode_returns_claims_for_valid_token(encode_data):
    assert decode_access_token(generate_access_token(encode_data, 15).token)["sub"] == encode_data["sub"]


def test_decode_returns_none_for_expired_token(encode_data):
    assert decode_access_token(generate_access_token(encode_data, -1).token) is None


def test_decode_returns_none_for_token_without_exp(encode_data):
    settings = get_settings()
    token = jwt.encode(encode_data, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)
    assert decode_access_token(token) is None


def test_decode_returns_none_for_garbage():
    assert decode_access_token("not-a-jwt") is None


# Authenticating access tokens


def test_authenticate_returns_ids_from_claims():
    ids = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = generate_access_token(
        {"sub": str(ids[0]), "profile_id": str(ids[1]), "session_id": str(ids[2]), "type": "access"}
    ).token
    assert authenticate_access_token(token) == ids


def test_expired_access_token_is_rejected(encode_data):
    token = generate_access_token({**encode_data, "session_id": str(uuid.uuid4())}, -1).token
    with pytest.raises(InvalidCredentialsError):
        authenticate_access_token(token)


def test_non_access_token_is_rejected(encode_data):
    token = generate_access_token({**encode_data, "session_id": str(uuid.uuid4()), "type": "refresh"}).token
    with pytest.raises(InvalidCredentialsError):
        authenticate_access_token(token)


def test_token_missing_an_id_claim_is_rejected(encode_data):
    with pytest.raises(InvalidCredentialsError):
        authenticate_access_token(generate_access_token(encode_data).token)


def test_garbage_token_is_rejected():
    with pytest.raises(InvalidCredentialsError):
        authenticate_access_token("not-a-jwt")
