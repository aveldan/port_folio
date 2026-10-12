"""Tests for AuthenticationService against the test database."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update

from app.core.security import (
    InvalidCredentialsError,
    authenticate_access_token,
    decode_access_token,
    hash_refresh_token,
)
from app.db.models import AuthSession
from app.schemas.requestDTOs.loginPwd import LoginPwdRequest
from app.schemas.requestDTOs.user import UserCreateRequest
from app.services.authenticationService import AuthenticationService
from app.services.userService import UserService

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"


@pytest.fixture
async def jane(db):
    return await UserService(db).create_user(
        UserCreateRequest(
            full_name="Jane Doe",
            birth_date="1990-05-01",
            email="jane@example.com",
            user_name="jane.doe",
            password=PASSWORD,
        )
    )


@pytest.fixture
async def tokens(db, jane):
    return await AuthenticationService(db).login_user_pwd(
        LoginPwdRequest(user_name="jane.doe", password=PASSWORD)
    )


async def _stored_session(db) -> AuthSession:
    # populate_existing so the row reflects the latest commit, not the identity map's copy.
    return (await db.scalars(select(AuthSession).execution_options(populate_existing=True))).one()


# Login


async def test_login_with_correct_password_returns_tokens_for_the_user(db, jane):
    user_id = jane.user_id
    tokens = await AuthenticationService(db).login_user_pwd(
        LoginPwdRequest(user_name="  Jane.DOE ", password=PASSWORD)
    )
    assert authenticate_access_token(tokens.access_token).user_id == user_id
    assert tokens.refresh_token


async def test_login_with_wrong_password_is_rejected(db, jane):
    with pytest.raises(InvalidCredentialsError):
        await AuthenticationService(db).login_user_pwd(LoginPwdRequest(user_name="jane.doe", password="wrong"))


async def test_login_with_unknown_user_name_is_rejected(db, jane):
    with pytest.raises(InvalidCredentialsError):
        await AuthenticationService(db).login_user_pwd(LoginPwdRequest(user_name="nobody", password=PASSWORD))


async def test_failed_login_creates_no_session(db, jane):
    with pytest.raises(InvalidCredentialsError):
        await AuthenticationService(db).login_user_pwd(LoginPwdRequest(user_name="jane.doe", password="wrong"))
    assert (await db.scalars(select(AuthSession))).all() == []


# Sessions and access tokens


async def test_generate_auth_session_stores_only_the_refresh_token_hash(db, tokens):
    stored = await _stored_session(db)
    assert stored.refresh_token == hash_refresh_token(tokens.refresh_token)
    assert stored.refresh_token != tokens.refresh_token
    assert stored.expires_at > datetime.now(timezone.utc) + timedelta(days=1)


async def test_token_response_expires_at_matches_access_token(tokens):
    claims = decode_access_token(tokens.access_token)
    assert tokens.expires_at.timestamp() == claims["exp"]


async def test_access_token_returns_its_session_creds(db, tokens):
    stored = await _stored_session(db)
    creds = authenticate_access_token(tokens.access_token)
    assert creds == (stored.user_id, stored.profile_id, stored.session_id)


async def test_access_token_is_checked_without_the_session_row(db, tokens):
    # Access tokens are stateless; the session row only matters when refreshing.
    await db.execute(delete(AuthSession))
    assert authenticate_access_token(tokens.access_token)


# Refresh


async def test_refresh_rotates_the_token_in_place(db, tokens):
    before = await _stored_session(db)
    session_id, expires_at, first = before.session_id, before.expires_at, before.first_token_assign_timestamp

    refreshed = await AuthenticationService(db).refresh_auth_session(tokens.refresh_token)

    after = await _stored_session(db)
    assert refreshed.refresh_token != tokens.refresh_token
    assert after.refresh_token == hash_refresh_token(refreshed.refresh_token)
    # Same session, same absolute expiry: refreshing doesn't extend the login.
    assert (after.session_id, after.expires_at, after.first_token_assign_timestamp) == (session_id, expires_at, first)
    assert authenticate_access_token(refreshed.access_token).session_id == session_id


async def test_old_refresh_token_stops_working_after_refresh(db, tokens):
    service = AuthenticationService(db)
    await service.refresh_auth_session(tokens.refresh_token)
    with pytest.raises(InvalidCredentialsError):
        await service.refresh_auth_session(tokens.refresh_token)


async def test_new_refresh_token_can_be_refreshed_again(db, tokens):
    service = AuthenticationService(db)
    refreshed = await service.refresh_auth_session(tokens.refresh_token)
    assert await service.refresh_auth_session(refreshed.refresh_token)


async def test_refresh_with_unknown_token_is_rejected(db, tokens):
    with pytest.raises(InvalidCredentialsError):
        await AuthenticationService(db).refresh_auth_session("not-a-real-token")


async def test_refresh_after_session_expires_is_rejected(db, tokens):
    await db.execute(update(AuthSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    with pytest.raises(InvalidCredentialsError):
        await AuthenticationService(db).refresh_auth_session(tokens.refresh_token)


async def test_refresh_after_logout_is_rejected(db, tokens):
    await db.execute(delete(AuthSession))
    with pytest.raises(InvalidCredentialsError):
        await AuthenticationService(db).refresh_auth_session(tokens.refresh_token)
