"""Tests for the /user routes."""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthProvider, Profile
from app.db.session import get_session
from app.main import app

pytestmark = pytest.mark.anyio

USER_URL = "/portfolio/v1/user"

VALID_USER = {
    "full_name": "Jane Doe",
    "birth_date": "1990-05-01",
    "email": "Jane@Example.com",
    "user_name": "Jane.Doe",
    "password": "correct horse battery",
}


@pytest.fixture
async def client(db: AsyncSession):
    """A client for the real app whose requests use the rolled-back test session."""
    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_create_user_returns_201_with_user(client, db: AsyncSession):
    resp = await client.post(USER_URL, json=VALID_USER)

    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "Jane Doe"
    assert body["email"] == "jane@example.com"
    assert body["birth_date"] == "1990-05-01"
    assert body["user_id"]

    profile = await db.scalar(select(Profile).where(Profile.identifier == "jane.doe"))
    assert profile is not None
    assert profile.provider == AuthProvider.PASSWORD
    assert str(profile.user_id) == body["user_id"]


async def test_create_user_never_returns_password(client):
    resp = await client.post(USER_URL, json=VALID_USER)

    assert "password" not in resp.json()
    assert VALID_USER["password"] not in resp.text


async def test_create_user_with_taken_email_returns_409(client):
    first = await client.post(USER_URL, json=VALID_USER)
    second = await client.post(USER_URL, json={**VALID_USER, "user_name": "someone.else"})

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["details"] == [{"field": "email", "message": "A user with this email already exists"}]


async def test_create_user_with_taken_user_name_returns_409(client):
    first = await client.post(USER_URL, json=VALID_USER)
    second = await client.post(USER_URL, json={**VALID_USER, "email": "other@example.com"})

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["details"] == [{"field": "user_name", "message": "This user name is already taken"}]


async def test_create_user_with_invalid_body_returns_422(client):
    resp = await client.post(USER_URL, json={**VALID_USER, "password": "short"})

    assert resp.status_code == 422
    assert resp.json()["details"][0]["field"] == "password"
