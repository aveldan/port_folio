"""Database tests for the Profile model."""

from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AuthProvider, Profile, User

pytestmark = pytest.mark.anyio


@pytest.fixture
async def people(db: AsyncSession) -> SimpleNamespace:
    """User A logs in with a password and Google, user B with a password, user C has no profiles."""
    a, b, c = User(full_name="User A"), User(full_name="User B"), User(full_name="User C")
    a_pwd = Profile(user=a, identifier="  Retirement ", secret="$argon2id$fake-a")
    a_google = Profile(user=a, provider=AuthProvider.GOOGLE, identifier="109876543210")
    b_pwd = Profile(user=b, identifier="bob", secret="$argon2id$fake-b")
    db.add_all([a, b, c, a_pwd, a_google, b_pwd])
    await db.flush()
    return SimpleNamespace(a=a, b=b, c=c, a_pwd=a_pwd, a_google=a_google, b_pwd=b_pwd)


# Defaults and normalization


async def test_provider_defaults_to_password(people):
    assert people.a_pwd.provider is AuthProvider.PASSWORD


async def test_identifier_is_trimmed_and_lowercased(people):
    assert people.a_pwd.identifier == "retirement"


async def test_timestamps_start_correctly(db, people):
    await db.refresh(people.a_pwd)
    assert people.a_pwd.created_timestamp is not None
    assert people.a_pwd.last_login_timestamp is None


# Relationship


async def test_user_loads_all_their_profiles(db, people):
    user_id = people.a.user_id
    db.expunge_all()
    user = (
        await db.scalars(select(User).where(User.user_id == user_id).options(selectinload(User.profiles)))
    ).one()
    assert sorted(p.provider for p in user.profiles) == [AuthProvider.GOOGLE, AuthProvider.PASSWORD]


# Rule: password profiles need a secret


async def test_password_profile_requires_secret(db, people, rejected_by):
    async with rejected_by("ck_folio_profiles_password_requires_secret"):
        db.add(Profile(user_id=people.c.user_id, identifier="nosecret"))


async def test_google_profile_does_not_need_secret(db, people):
    db.add(Profile(user_id=people.c.user_id, provider=AuthProvider.GOOGLE, identifier="333333333333"))
    await db.flush()


# Rule: an identifier is unique per provider, across all users


async def test_username_cannot_be_reused_in_any_case(db, people, rejected_by):
    async with rejected_by("uq_folio_profiles_provider_identifier"):
        db.add(Profile(user_id=people.c.user_id, identifier="RETIREMENT", secret="x"))


async def test_google_account_cannot_be_reused(db, people, rejected_by):
    async with rejected_by("uq_folio_profiles_provider_identifier"):
        db.add(Profile(user_id=people.c.user_id, provider=AuthProvider.GOOGLE, identifier="109876543210"))


async def test_same_identifier_allowed_under_different_provider(db, people):
    db.add(Profile(user_id=people.c.user_id, provider=AuthProvider.GOOGLE, identifier="retirement"))
    await db.flush()


# Rule: one profile per provider per user


async def test_user_cannot_have_second_password_profile(db, people, rejected_by):
    async with rejected_by("uq_folio_profiles_user_id_provider"):
        db.add(Profile(user_id=people.a.user_id, identifier="another-username", secret="x"))


async def test_user_cannot_have_second_google_profile(db, people, rejected_by):
    async with rejected_by("uq_folio_profiles_user_id_provider"):
        db.add(Profile(user_id=people.a.user_id, provider=AuthProvider.GOOGLE, identifier="222222222222"))


async def test_different_users_can_each_have_password_profile(db, people):
    password_profiles = await db.scalar(
        select(func.count()).select_from(Profile).where(Profile.provider == AuthProvider.PASSWORD)
    )
    assert password_profiles == 2


# Rule: deleting a user deletes their profiles


async def test_deleting_user_deletes_their_profiles(db, people):
    user_id = people.a.user_id
    await db.execute(delete(User).where(User.user_id == user_id))
    remaining = await db.scalar(select(func.count()).select_from(Profile).where(Profile.user_id == user_id))
    assert remaining == 0