import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.profile import Profile
    from app.db.models.user import User


class AuthSession(Base):
    """One logged-in device/browser, holding the current refresh token for JWT auth.
    The refresh token is rotated on every refresh, so only the latest one is kept here.
    """

    __tablename__ = "folio_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "user_id"],
            ["folio_profiles.profile_id", "folio_profiles.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "first_token_assign_timestamp <= latest_token_assign_timestamp",
            name="first_token_before_latest",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("folio_users.user_id", ondelete="CASCADE"),
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    refresh_token: Mapped[str] = mapped_column(Text, unique=True)
    first_token_assign_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    latest_token_assign_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    user: Mapped["User"] = relationship(back_populates="sessions", lazy="raise")
    profile: Mapped["Profile"] = relationship(
        back_populates="sessions", lazy="raise", overlaps="user,sessions"
    )

    def __repr__(self) -> str:
        return (
            f"AuthSession(session_id={self.session_id!r}, user_id={self.user_id!r}, "
            f"profile_id={self.profile_id!r})"
        )
