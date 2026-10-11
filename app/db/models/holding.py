import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.account import Account
    from app.db.models.assets import Asset

MONEY = Numeric(20, 8)


class Holding(Base):
    """The net position of one asset in one account, after applying all of its transactions."""

    __tablename__ = "folio_holdings"
    __table_args__ = (
        UniqueConstraint("account_id", "asset_id", name="uq_folio_holdings_account_id_asset_id"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("avg_price >= 0", name="avg_price_non_negative"),
        CheckConstraint(
            "first_transaction_timestamp <= last_transaction_timestamp",
            name="first_transaction_before_last",
        ),
    )

    holding_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("folio_accounts.account_id", ondelete="RESTRICT"),
    )
    asset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("folio_assets.asset_id", ondelete="RESTRICT"),
        index=True,
    )
    quantity: Mapped[Decimal] = mapped_column(MONEY)
    avg_price: Mapped[Decimal] = mapped_column(MONEY)
    first_transaction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_transaction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_update_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped["Account"] = relationship(back_populates="holdings", lazy="raise")
    asset: Mapped["Asset"] = relationship(back_populates="holdings", lazy="raise")

    def __repr__(self) -> str:
        return (
            f"Holding(holding_id={self.holding_id!r}, account_id={self.account_id!r}, "
            f"asset_id={self.asset_id!r}, quantity={self.quantity!r}, avg_price={self.avg_price!r})"
        )