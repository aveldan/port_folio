import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.accountUser import account_users

if TYPE_CHECKING:
    from app.db.models.holding import Holding
    from app.db.models.transaction import Transaction
    from app.db.models.user import User


class Account(Base):
    """A named bucket of money, e.g. "Brokerage", "Roth IRA", "Emergency savings".

    An account can be held by several users, e.g. a joint account.
    """

    __tablename__ = "folio_accounts"

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    account_name: Mapped[str] = mapped_column(String(100))
    created_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    users: Mapped[list["User"]] = relationship(
        secondary=account_users, back_populates="accounts", lazy="raise", passive_deletes=True
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", lazy="raise"
    )
    holdings: Mapped[list["Holding"]] = relationship(back_populates="account", lazy="raise")

    def __repr__(self) -> str:
        return f"Account(account_id={self.account_id!r}, account_name={self.account_name!r})"