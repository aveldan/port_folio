import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class AuthProvider(str, enum.Enum):
    PASSWORD = "password"
    GOOGLE = "google"


class Profile(Base):
    """A separate space for a user's funds, each with its own login. A user can have many."""

    __tablename__ = "folio_profiles"
    __table_args__ = (
        UniqueConstraint("profile_id", "user_id", name="uq_folio_profiles_profile_id_user_id"),
        # A login identifier is unique per provider: username "bob" and a Google id can't clash.
        UniqueConstraint("provider", "identifier", name="uq_folio_profiles_provider_identifier"),
        # Password logins must have a hash; other providers authenticate elsewhere.
        CheckConstraint(
            "provider <> 'password' OR secret IS NOT NULL",
            name="password_requires_secret",
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # Many profiles per user; deleting the user deletes all their profiles.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("folio_users.user_id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(
            AuthProvider,
            name="auth_provider",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=AuthProvider.PASSWORD,
        server_default=AuthProvider.PASSWORD.value,
    )
    identifier: Mapped[str] = mapped_column(String(255))
    secret: Mapped[str | None] = mapped_column(String(255))
    created_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="profiles", lazy="raise")

    @validates("identifier")
    def _normalize_identifier(self, key: str, value: str) -> str:
        return value.strip().lower() if value else value

    def __repr__(self) -> str:
        return (
            f"Profile(profile_id={self.profile_id!r}, provider={self.provider!r}, "
            f"identifier={self.identifier!r})"
        )
