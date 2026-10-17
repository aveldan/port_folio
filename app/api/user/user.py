from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.requestDTOs.user import UserCreateRequest
from app.schemas.responseDTOs.user import UserResponse
from app.services.userService import UserService

router = APIRouter(prefix="/user", tags=["user"])


def get_user_service(session: Annotated[AsyncSession, Depends(get_session)]) -> UserService:
    return UserService(session)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreateRequest,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Create a new user with a user name/password login.

    A duplicate email or user name comes back as a 409 from the IntegrityError handler.
    """
    user = await user_service.create_user(request)
    return UserResponse.model_validate(user)
