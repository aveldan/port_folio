from typing import TYPE_CHECKING

from sqlalchemy import Identity, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.assets import Asset


class AssetType(Base):
    """Reference table of asset categories, e.g. ETF, Stock, Commodity, Bond, Cash."""

    __tablename__ = "folio_asset_types"

    asset_type_id: Mapped[int] = mapped_column(
        SmallInteger, Identity(), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    assets: Mapped[list["Asset"]] = relationship(back_populates="asset_type", lazy="raise")

    def __repr__(self) -> str:
        return f"AssetType(asset_type_id={self.asset_type_id!r}, name={self.name!r})"