import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """A user as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    full_name: str
    birth_date: date | None
    email: str | None
    avatar_url: str | None
