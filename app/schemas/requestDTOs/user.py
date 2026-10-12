import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, Secret, StringConstraints, field_validator

USER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

Password = Secret[Annotated[str, StringConstraints(strip_whitespace=False, min_length=8, max_length=128)]]


class UserCreateRequest(BaseModel):
    """Payload received by the API to create a user."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    birth_date: date
    email: EmailStr = Field(max_length=200)
    user_name: str = Field(min_length=3, max_length=30)
    password: Password

    @field_validator("birth_date")
    @classmethod
    def _birth_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("birth_date cannot be in the future")
        return value

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("user_name")
    @classmethod
    def _normalize_user_name(cls, value: str) -> str:
        if not USER_NAME_PATTERN.fullmatch(value):
            raise ValueError("user_name may only contain letters, numbers, '.', '_' and '-'")
        return value.lower()