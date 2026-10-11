from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Identity, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.assetTypes import AssetType
    from app.db.models.transaction import Transaction


class Asset(Base):
    """Reference table of individual instruments, e.g. VOO on NYSE Arca, Gold, a fixed deposit."""

    __tablename__ = "folio_assets"
    __table_args__ = (
        # The same ticker can be listed on several exchanges, so uniqueness is on the pair.
        UniqueConstraint("ticker", "exchange", name="uq_folio_assets_ticker_exchange"),
    )

    asset_id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    asset_type_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("folio_asset_types.asset_type_id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Optional: fixed deposits, savings and many bonds have no ticker or exchange.
    ticker: Mapped[str | None] = mapped_column(String(20))
    exchange: Mapped[str | None] = mapped_column(String(20))

    asset_type: Mapped["AssetType"] = relationship(back_populates="assets", lazy="raise")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="asset", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"Asset(asset_id={self.asset_id!r}, name={self.name!r}, ticker={self.ticker!r})"