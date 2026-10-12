"""Tests for UserService against the test database."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import AuthProvider, Profile, User
from app.schemas.requestDTOs.user import UserCreateRequest
from app.services.userService import UserService, password_hash

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"


def _request(**overrides) -> UserCreateRequest:
    data = {
        "full_name": "Jane Doe",
        "birth_date": "1990-05-01",
        "email": "jane@example.com",
        "user_name": "Jane.Doe",
        "password": PASSWORD,
    } | overrides
    return UserCreateRequest(**data)


async def _count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_create_user_stores_user_fields(db):
    user = await UserService(db).create_user(_request())
    assert isinstance(user.user_id, uuid.UUID)
    assert (user.full_name, str(user.birth_date), user.email) == ("Jane Doe", "1990-05-01", "jane@example.com")


async def test_create_user_adds_password_profile_with_hash(db):
    user = await UserService(db).create_user(_request())
    profile = (await db.scalars(select(Profile).where(Profile.user_id == user.user_id))).one()
    assert profile.provider == AuthProvider.PASSWORD
    assert profile.identifier == "jane.doe"
    assert profile.secret != PASSWORD
    assert profile.secret.startswith("$argon2")
    assert password_hash.verify(PASSWORD, profile.secret)
    assert not password_hash.verify("wrong password", profile.secret)


async def test_duplicate_user_name_is_rejected_and_nothing_is_saved(db):
    service = UserService(db)
    await service.create_user(_request())
    with pytest.raises(IntegrityError, match="uq_folio_profiles_provider_identifier"):
        await service.create_user(_request(email="other@example.com", user_name="JANE.DOE"))
    # The second user row was rolled back along with its profile.
    assert await _count(db, User) == 1
    assert await _count(db, Profile) == 1


async def test_duplicate_email_is_rejected(db):
    service = UserService(db)
    await service.create_user(_request())
    with pytest.raises(IntegrityError, match="ix_folio_users_email"):
        await service.create_user(_request(user_name="someone.else"))
    assert await _count(db, User) == 1


async def test_session_is_usable_after_a_failed_create(db):
    service = UserService(db)
    await service.create_user(_request())
    with pytest.raises(IntegrityError):
        await service.create_user(_request(user_name="someone.else"))
    other = await service.create_user(_request(email="other@example.com", user_name="other"))
    assert other.user_id is not None
