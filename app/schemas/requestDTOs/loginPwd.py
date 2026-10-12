from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, Secret, StringConstraints, field_validator

LoginPassword = Secret[Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=128)]]


class LoginPwdRequest(BaseModel):
    """Payload received by the API to log in with a user name and password."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    user_name: str = Field(min_length=1, max_length=30)
    password: LoginPassword

    @field_validator("user_name")
    @classmethod
    def _normalize_user_name(cls, value: str) -> str:
        return value.lower()