"""Tests for the app-wide exception handlers in app.api.errors."""

from datetime import date, timedelta

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import register_exception_handlers
from app.db.models import User
from app.schemas.requestDTOs.user import UserCreateRequest

pytestmark = pytest.mark.anyio

VALID_USER = {
    "full_name": "Jane Doe",
    "birth_date": "1990-05-01",
    "email": "jane@example.com",
    "user_name": "jane.doe",
    "password": "correct horse battery",
}


@pytest.fixture
def make_client():
    """Build an httpx client for a throwaway app that has the real exception handlers."""

    def _make_client(app: FastAPI) -> httpx.AsyncClient:
        register_exception_handlers(app)
        # raise_app_exceptions=False lets us see the 500 response instead of the re-raised error.
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return _make_client


@pytest.fixture
def client(make_client):
    app = FastAPI()

    @app.post("/users")
    async def create_user(payload: UserCreateRequest):
        return payload

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="User not found")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    return make_client(app)


@pytest.fixture
def db_client(make_client, db: AsyncSession):
    """A client whose route writes straight to the test database, bypassing DTO validation."""
    app = FastAPI()

    @app.post("/raw-users")
    async def create_raw_user(body: dict):
        db.add(User(full_name=body["full_name"], email=body.get("email"),
                    birth_date=date.fromisoformat(body["birth_date"]) if "birth_date" in body else None))
        await db.flush()
        return {"ok": True}

    return make_client(app)


# Request validation


async def test_valid_request_passes_through(client):
    async with client:
        resp = await client.post("/users", json=VALID_USER)
    assert resp.status_code == 200


async def test_validation_errors_list_each_field(client):
    bad = {"full_name": "", "birth_date": "not-a-date", "email": "nope", "user_name": "a b", "password": "short"}
    async with client:
        resp = await client.post("/users", json=bad)
    body = resp.json()
    assert resp.status_code == 422
    assert body["code"] == "validation_error"
    assert {d["field"] for d in body["details"]} == {"full_name", "birth_date", "email", "user_name", "password"}


async def test_custom_validator_message_has_no_pydantic_prefix(client):
    future = (date.today() + timedelta(days=1)).isoformat()
    async with client:
        resp = await client.post("/users", json={**VALID_USER, "birth_date": future})
    assert resp.json()["details"] == [{"field": "birth_date", "message": "birth_date cannot be in the future"}]


async def test_missing_and_extra_fields_are_reported(client):
    async with client:
        resp = await client.post("/users", json={"full_name": "Jane", "birth_date": "1990-01-01", "nickname": "J"})
    fields = {d["field"] for d in resp.json()["details"]}
    assert fields == {"email", "user_name", "password", "nickname"}


# HTTP errors and crashes


async def test_password_is_never_echoed_back(client):
    async with client:
        resp = await client.post("/users", json=VALID_USER)
    assert VALID_USER["password"] not in resp.text


async def test_http_exception_keeps_status_and_message(client):
    async with client:
        resp = await client.get("/missing")
    assert resp.status_code == 404
    assert resp.json() == {"code": "http_error", "message": "User not found", "details": []}


async def test_unknown_route_uses_same_shape(client):
    async with client:
        resp = await client.get("/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == "http_error"


async def test_unhandled_error_hides_internal_details(client):
    async with client:
        resp = await client.get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"code": "internal_error", "message": "An unexpected error occurred", "details": []}


# Database integrity errors


async def test_duplicate_email_returns_409(db_client):
    async with db_client:
        first = await db_client.post("/raw-users", json={"full_name": "A", "email": "dup@example.com"})
        second = await db_client.post("/raw-users", json={"full_name": "B", "email": "dup@example.com"})
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json() == {
        "code": "conflict",
        "message": "A user with this email already exists",
        "details": [{"field": "email", "message": "A user with this email already exists"}],
    }


async def test_db_check_constraint_returns_422(db_client):
    async with db_client:
        resp = await db_client.post("/raw-users", json={"full_name": "A", "birth_date": "2999-01-01"})
    assert resp.status_code == 422
    assert resp.json()["details"] == [{"field": "birth_date", "message": "birth_date cannot be in the future"}]
