import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.account import Account
    from app.db.models.profile import Profile


class User(Base):
    """A person who owns portfolios in the app."""

    __tablename__ = "folio_users"
    __table_args__ = (
        CheckConstraint("birth_date <= CURRENT_DATE", name="birth_date_not_in_future"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    full_name: Mapped[str] = mapped_column(String(200))
    birth_date: Mapped[date | None] = mapped_column(Date)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(200), unique=True, index=True)

    profiles: Mapped[list["Profile"]] = relationship(
        back_populates="user", lazy="raise", passive_deletes=True
    )
    accounts: Mapped[list["Account"]] = relationship(back_populates="user", lazy="raise")

    @validates("email")
    def _normalize_email(self, key: str, value: str | None) -> str | None:
        return value.strip().lower() if value else value
    
    def __repr__(self) -> str:
        return f"User(user_id={self.user_id!r}, full_name={self.full_name!r})"