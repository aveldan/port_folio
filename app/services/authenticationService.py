from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tomlkit import datetime

from app.config import get_settings
from app.core.security import DUMMY_HASH, generate_refresh_token, generate_token, verify_password
from app.db.models import AuthProvider, Profile
from app.db.models.authSessions import AuthSession
from app.schemas.requestDTOs.loginPwd import LoginPwdRequest
from app.schemas.responseDTOs.token import TokenResponse


class AuthenticationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def login_user_pwd(self, request: LoginPwdRequest) -> Profile | None:
        password = request.password.get_secret_value()
        profile = await self.session.scalar(
            select(Profile)
            .where(Profile.provider == AuthProvider.PASSWORD, Profile.identifier == request.user_name)
            .options(selectinload(Profile.user))
        )
        if profile is None: # timing attack mitigation
            await verify_password(password, DUMMY_HASH)
            return None
        if await verify_password(password, profile.secret):
            return profile
        return None
    
    async def generate_auth_session(self, profile: Profile) -> str:
        refresh_token = generate_refresh_token()
        auth_session = AuthSession(
            user_id=profile.user_id,
            profile_id=profile.profile_id,
            refresh_token=refresh_token,
            expires_at=datetime.now(tz=get_settings().timezone) + timedelta(days=get_settings().jwt_refresh_token_expire_days)
        )
        self.session.add(auth_session)
        await self.session.commit()
        
        encode_data = {
            "sub": str(profile.user_id),
            "profile_id": str(profile.profile_id),
            "session_id": str(auth_session.session_id),
            "type": "access",
        }
        access_token = generate_token(encode_data)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=get_settings().jwt_access_token_expire_minutes * 60,
        )