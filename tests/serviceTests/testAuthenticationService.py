"""Tests for AuthenticationService against the test database."""

import pytest

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


async def test_login_with_correct_password_returns_user(db, jane):
    user = await AuthenticationService(db).login_user_pwd(
        LoginPwdRequest(user_name="  Jane.DOE ", password=PASSWORD)
    )
    assert user is not None and user.user_id == jane.user_id


async def test_login_with_wrong_password_returns_none(db, jane):
    request = LoginPwdRequest(user_name="jane.doe", password="wrong")
    assert await AuthenticationService(db).login_user_pwd(request) is None


async def test_login_with_unknown_user_name_returns_none(db, jane):
    request = LoginPwdRequest(user_name="nobody", password=PASSWORD)
    assert await AuthenticationService(db).login_user_pwd(request) is None
