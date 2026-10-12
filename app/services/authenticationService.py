from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import (
    DUMMY_HASH,
    InvalidCredentialsError,
    generate_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.db.models import AuthProvider, AuthSession, Profile
from app.schemas.requestDTOs.loginPwd import LoginPwdRequest
from app.schemas.responseDTOs.token import TokenResponse


class AuthenticationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def login_user_pwd(self, request: LoginPwdRequest) -> TokenResponse:
        password = request.password.get_secret_value()
        profile = await self.session.scalar(
            select(Profile)
            .where(Profile.provider == AuthProvider.PASSWORD, Profile.identifier == request.user_name)
        )
        if profile is None: # timing attack mitigation
            await verify_password(password, DUMMY_HASH)
            raise InvalidCredentialsError()
        if await verify_password(password, profile.secret):
            return await self.generate_auth_session(profile)
        raise InvalidCredentialsError()
    
    async def logout_session(self, refresh_token: str) -> None:
        await self.session.execute(
            delete(AuthSession).where(AuthSession.refresh_token == hash_refresh_token(refresh_token))
        )
        await self.session.commit()

    async def generate_auth_session(self, profile: Profile) -> TokenResponse:
        settings = get_settings()
        refresh_token = generate_refresh_token()
        auth_session = AuthSession(
            user_id=profile.user_id,
            profile_id=profile.profile_id,
            refresh_token=hash_refresh_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
        self.session.add(auth_session)
        await self.session.flush()

        access_token = generate_access_token(
            {
                "sub": str(auth_session.user_id),
                "profile_id": str(auth_session.profile_id),
                "session_id": str(auth_session.session_id),
                "type": "access",
            }
        )
        await self.session.commit()

        return TokenResponse(
            access_token=access_token.token,
            refresh_token=refresh_token,
            expires_at=access_token.expires_at,
        )

    async def refresh_auth_session(self, refresh_token: str) -> TokenResponse:
        auth_session = await self.session.scalar(
            select(AuthSession)
            .where(
                AuthSession.refresh_token == hash_refresh_token(refresh_token),
                AuthSession.expires_at > datetime.now(timezone.utc),
            )
            .with_for_update()
        )
        if auth_session is None:
            raise InvalidCredentialsError()

        new_refresh_token = generate_refresh_token()
        auth_session.refresh_token = hash_refresh_token(new_refresh_token)
        auth_session.latest_token_assign_timestamp = datetime.now(timezone.utc)
        await self.session.flush()

        access_token = generate_access_token(
            {
                "sub": str(auth_session.user_id),
                "profile_id": str(auth_session.profile_id),
                "session_id": str(auth_session.session_id),
                "type": "access",
            }
        )
        await self.session.commit()

        return TokenResponse(
            access_token=access_token.token,
            refresh_token=new_refresh_token,
            expires_at=access_token.expires_at,
        )