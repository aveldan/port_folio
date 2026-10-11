import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.holding import Holding
    from app.db.models.transaction import Transaction
    from app.db.models.user import User


class Account(Base):
    """A named bucket of a user's money, e.g. "Brokerage", "Roth IRA", "Emergency savings"."""

    __tablename__ = "folio_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "account_name", name="uq_folio_accounts_user_id_account_name"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("folio_users.user_id", ondelete="RESTRICT"),
        index=True,
    )
    account_name: Mapped[str] = mapped_column(String(100))
    created_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="accounts", lazy="raise")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", lazy="raise"
    )
    holdings: Mapped[list["Holding"]] = relationship(back_populates="account", lazy="raise")

    def __repr__(self) -> str:
        return f"Account(account_id={self.account_id!r}, account_name={self.account_name!r})"