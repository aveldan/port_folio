"""Database tests for the AuthSession model."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AuthProvider, AuthSession, Profile, User

EXPIRES_AT = datetime.now(timezone.utc) + timedelta(days=30)

pytestmark = pytest.mark.anyio


@pytest.fixture
async def people(db: AsyncSession) -> SimpleNamespace:
    """User A is logged in with password on one device and Google on another; user B has no sessions."""
    a, b = User(full_name="User A"), User(full_name="User B")
    a_pwd = Profile(user=a, identifier="alice", secret="$argon2id$fake-a")
    a_google = Profile(user=a, provider=AuthProvider.GOOGLE, identifier="109876543210")
    b_pwd = Profile(user=b, identifier="bob", secret="$argon2id$fake-b")
    db.add_all([a, b, a_pwd, a_google, b_pwd])
    await db.flush()
    laptop = AuthSession(user_id=a.user_id, profile_id=a_pwd.profile_id, refresh_token="hash-laptop", expires_at=EXPIRES_AT)
    phone = AuthSession(user_id=a.user_id, profile_id=a_google.profile_id, refresh_token="hash-phone", expires_at=EXPIRES_AT)
    db.add_all([laptop, phone])
    await db.flush()
    return SimpleNamespace(
        a=a, b=b, a_pwd=a_pwd, a_google=a_google, b_pwd=b_pwd, laptop=laptop, phone=phone
    )


# Defaults


async def test_ids_and_timestamps_start_correctly(db, people):
    await db.refresh(people.laptop)
    assert people.laptop.session_id is not None
    assert people.laptop.first_token_assign_timestamp is not None
    assert people.laptop.first_token_assign_timestamp == people.laptop.latest_token_assign_timestamp


# Relationships


async def test_user_loads_all_their_sessions(db, people):
    user_id = people.a.user_id
    db.expunge_all()
    user = (
        await db.scalars(select(User).where(User.user_id == user_id).options(selectinload(User.sessions)))
    ).one()
    assert sorted(s.refresh_token for s in user.sessions) == ["hash-laptop", "hash-phone"]


async def test_session_knows_which_profile_logged_in(db, people):
    session_id = people.phone.session_id
    db.expunge_all()
    session = (
        await db.scalars(
            select(AuthSession)
            .where(AuthSession.session_id == session_id)
            .options(selectinload(AuthSession.profile))
        )
    ).one()
    assert session.profile.provider is AuthProvider.GOOGLE


# Rule: the profile must belong to the session's user


async def test_profile_of_another_user_is_rejected(db, people, rejected_by):
    async with rejected_by("fk_folio_sessions_profile_id_folio_profiles"):
        db.add(
            AuthSession(
                user_id=people.a.user_id, profile_id=people.b_pwd.profile_id, refresh_token="hash-x",
                expires_at=EXPIRES_AT,
            )
        )


# Rule: a refresh token identifies exactly one session


async def test_refresh_token_cannot_be_reused(db, people, rejected_by):
    async with rejected_by("uq_folio_sessions_refresh_token"):
        db.add(
            AuthSession(
                user_id=people.b.user_id, profile_id=people.b_pwd.profile_id, refresh_token="hash-laptop",
                expires_at=EXPIRES_AT,
            )
        )


async def test_rotating_token_moves_latest_timestamp(db, people):
    await db.refresh(people.laptop)
    rotated_at = people.laptop.first_token_assign_timestamp + timedelta(minutes=15)
    people.laptop.refresh_token = "hash-laptop-2"
    people.laptop.latest_token_assign_timestamp = rotated_at
    await db.flush()
    await db.refresh(people.laptop)
    assert people.laptop.latest_token_assign_timestamp == rotated_at


# Rule: the first token can't be assigned after the latest one


async def test_latest_token_cannot_predate_first(db, people, rejected_by):
    await db.refresh(people.laptop)
    async with rejected_by("ck_folio_sessions_first_token_before_latest"):
        people.laptop.latest_token_assign_timestamp = (
            people.laptop.first_token_assign_timestamp - timedelta(seconds=1)
        )


# Rule: deleting a user or a profile ends their sessions


async def test_deleting_user_deletes_their_sessions(db, people):
    user_id = people.a.user_id
    await db.execute(delete(User).where(User.user_id == user_id))
    remaining = await db.scalar(
        select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id)
    )
    assert remaining == 0


async def test_deleting_profile_deletes_only_its_sessions(db, people):
    await db.execute(delete(Profile).where(Profile.profile_id == people.a_google.profile_id))
    tokens = await db.scalars(
        select(AuthSession.refresh_token).where(AuthSession.user_id == people.a.user_id)
    )
    assert list(tokens) == ["hash-laptop"]
