import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.account import Account
    from app.db.models.assets import Asset

MONEY = Numeric(20, 8)


class TransactionSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class Transaction(Base):
    """A single buy or sell of an asset, recorded against one account."""

    __tablename__ = "folio_transactions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price_per_count >= 0", name="price_non_negative"),
        CheckConstraint("commission >= 0", name="commission_non_negative"),
    )

    transaction_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # RESTRICT: an account with transaction history can't be deleted by accident.
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("folio_accounts.account_id", ondelete="RESTRICT"),
        index=True,
    )
    asset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("folio_assets.asset_id", ondelete="RESTRICT"),
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    transaction_side: Mapped[TransactionSide] = mapped_column(
        Enum(
            TransactionSide,
            name="transaction_side",
            native_enum=False,
            create_constraint=True,
            length=10,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    quantity: Mapped[Decimal] = mapped_column(MONEY)
    price_per_count: Mapped[Decimal] = mapped_column(MONEY)
    commission: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    total_price: Mapped[Decimal] = mapped_column(
        MONEY,
        Computed(
            "CASE WHEN transaction_side = 'buy' "
            "THEN quantity * price_per_count + commission "
            "ELSE quantity * price_per_count - commission END",
            persisted=True,
        ),
    )
    comment: Mapped[str | None] = mapped_column(Text)

    account: Mapped["Account"] = relationship(back_populates="transactions", lazy="raise")
    asset: Mapped["Asset"] = relationship(back_populates="transactions", lazy="raise")

    def __repr__(self) -> str:
        return (
            f"Transaction(transaction_id={self.transaction_id!r}, account_id={self.account_id!r}, "
            f"asset_id={self.asset_id!r}, "
            f"side={self.transaction_side.value if self.transaction_side else None!r}, "
            f"quantity={self.quantity!r}, price_per_count={self.price_per_count!r})"
        )