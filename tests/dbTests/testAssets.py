"""Database tests for the Asset model's market price columns."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Asset, AssetType, Holding, User

pytestmark = pytest.mark.anyio

PRICE_TS = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
async def etf(db: AsyncSession) -> AssetType:
    asset_type = AssetType(name="ETF")
    db.add(asset_type)
    await db.flush()
    return asset_type


def _voo(etf: AssetType, **overrides) -> Asset:
    fields = dict(name="Vanguard S&P 500", ticker="VOO", exchange="NYSEARCA", asset_type=etf)
    fields.update(overrides)
    return Asset(**fields)


async def _save(db: AsyncSession, asset: Asset) -> Asset:
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


async def test_new_asset_has_no_market_price(db, etf):
    asset = await _save(db, _voo(etf))
    assert asset.market_price is None
    assert asset.market_price_update_timestamp is None


async def test_market_price_round_trips_exactly(db, etf):
    asset = await _save(db, _voo(etf, market_price=Decimal("523.12345678"), market_price_update_timestamp=PRICE_TS))
    assert asset.market_price == Decimal("523.12345678")
    assert asset.market_price_update_timestamp == PRICE_TS


async def test_market_price_can_be_updated(db, etf):
    asset = await _save(db, _voo(etf, market_price=Decimal("500"), market_price_update_timestamp=PRICE_TS))
    later = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)
    asset.market_price = Decimal("510.50")
    asset.market_price_update_timestamp = later
    await db.flush()
    await db.refresh(asset)
    assert (asset.market_price, asset.market_price_update_timestamp) == (Decimal("510.50"), later)


async def test_zero_market_price_is_allowed(db, etf):
    asset = await _save(db, _voo(etf, market_price=Decimal("0"), market_price_update_timestamp=PRICE_TS))
    assert asset.market_price == Decimal("0")


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        pytest.param(
            dict(market_price=Decimal("-1"), market_price_update_timestamp=PRICE_TS),
            "ck_folio_assets_market_price_non_negative",
            id="negative-price",
        ),
        pytest.param(
            dict(market_price=Decimal("500")),
            "ck_folio_assets_market_price_has_timestamp",
            id="price-without-timestamp",
        ),
        pytest.param(
            dict(market_price_update_timestamp=PRICE_TS),
            "ck_folio_assets_market_price_has_timestamp",
            id="timestamp-without-price",
        ),
    ],
)
async def test_invalid_market_price_is_rejected(db, etf, rejected_by, overrides, constraint):
    async with rejected_by(constraint):
        db.add(_voo(etf, **overrides))


# Changing an existing price


async def _priced_voo(db: AsyncSession, etf: AssetType) -> Asset:
    return await _save(db, _voo(etf, market_price=Decimal("500"), market_price_update_timestamp=PRICE_TS))


async def test_price_can_be_cleared_with_its_timestamp(db, etf):
    asset = await _priced_voo(db, etf)
    asset.market_price = None
    asset.market_price_update_timestamp = None
    await db.flush()
    await db.refresh(asset)
    assert (asset.market_price, asset.market_price_update_timestamp) == (None, None)


@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        pytest.param(dict(market_price=None), "ck_folio_assets_market_price_has_timestamp", id="clear-price-only"),
        pytest.param(
            dict(market_price_update_timestamp=None),
            "ck_folio_assets_market_price_has_timestamp",
            id="clear-timestamp-only",
        ),
        pytest.param(dict(market_price=Decimal("-0.01")), "ck_folio_assets_market_price_non_negative", id="set-negative"),
    ],
)
async def test_invalid_price_update_is_rejected(db, etf, rejected_by, changes, constraint):
    asset = await _priced_voo(db, etf)
    async with rejected_by(constraint):
        for field, value in changes.items():
            setattr(asset, field, value)
    # The savepoint rolled back, so the stored price is untouched.
    await db.refresh(asset)
    assert (asset.market_price, asset.market_price_update_timestamp) == (Decimal("500"), PRICE_TS)


# Precision and range of Numeric(20, 8)


async def test_price_beyond_eight_decimals_is_rounded(db, etf):
    asset = await _save(
        db, _voo(etf, market_price=Decimal("0.123456785"), market_price_update_timestamp=PRICE_TS)
    )
    assert asset.market_price == Decimal("0.12345679")


async def test_largest_price_that_fits_is_stored(db, etf):
    largest = Decimal("999999999999.99999999")
    asset = await _save(db, _voo(etf, market_price=largest, market_price_update_timestamp=PRICE_TS))
    assert asset.market_price == largest


async def test_price_too_large_overflows(db, etf):
    with pytest.raises(DBAPIError, match="numeric field overflow"):
        async with db.begin_nested():
            db.add(_voo(etf, market_price=Decimal("1000000000000"), market_price_update_timestamp=PRICE_TS))
            await db.flush()


async def test_timestamp_keeps_the_same_instant_across_timezones(db, etf):
    new_york = timezone(timedelta(hours=-4))
    quoted_at = datetime(2026, 10, 10, 16, 0, tzinfo=new_york)
    asset = await _save(db, _voo(etf, market_price=Decimal("500"), market_price_update_timestamp=quoted_at))
    assert asset.market_price_update_timestamp == PRICE_TS


# Using the price


async def test_one_price_values_holdings_in_every_account(db, etf):
    user = User(full_name="Test User")
    brokerage = Account(users=[user], account_name="Brokerage")
    ira = Account(users=[user], account_name="Roth IRA")
    asset = _voo(etf, market_price=Decimal("520.25"), market_price_update_timestamp=PRICE_TS)
    db.add_all([user, brokerage, ira, asset])
    await db.flush()
    for account, quantity in [(brokerage, "10"), (ira, "2.5")]:
        db.add(
            Holding(
                account_id=account.account_id,
                asset_id=asset.asset_id,
                quantity=Decimal(quantity),
                avg_price=Decimal("500"),
                first_transaction_timestamp=PRICE_TS,
                last_transaction_timestamp=PRICE_TS,
            )
        )
    await db.flush()

    rows = await db.execute(
        select(Account.account_name, Holding.quantity * Asset.market_price)
        .join(Holding, Holding.account_id == Account.account_id)
        .join(Asset, Asset.asset_id == Holding.asset_id)
    )
    assert dict(rows.all()) == {"Brokerage": Decimal("5202.50"), "Roth IRA": Decimal("1300.625")}
