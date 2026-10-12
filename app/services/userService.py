from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models import AuthProvider, Profile, User
from app.schemas.requestDTOs.user import UserCreateRequest


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_user(self, request: UserCreateRequest) -> User:
        """Create a user and their user name/password login, and commit both together.

        Raises IntegrityError if the email or user name is already taken; the API's
        exception handler turns that into a 409.
        """
        hashed = await hash_password(request.password.get_secret_value())

        user = User(
            full_name=request.full_name,
            birth_date=request.birth_date,
            email=request.email,
            profiles=[Profile(provider=AuthProvider.PASSWORD, identifier=request.user_name, secret=hashed)],
        )
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        await self.session.refresh(user)
        return user