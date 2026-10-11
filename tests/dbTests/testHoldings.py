"""Database tests for the Holding model."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Account, Asset, AssetType, Holding, User

pytestmark = pytest.mark.anyio

FIRST_TS = datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc)
LAST_TS = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
async def setup(db: AsyncSession) -> SimpleNamespace:
    """A user with a Brokerage and a Roth IRA account, and two ETFs to hold."""
    user = User(full_name="Test User")
    brokerage = Account(user=user, account_name="Brokerage")
    ira = Account(user=user, account_name="Roth IRA")
    etf = AssetType(name="ETF")
    voo = Asset(name="Vanguard S&P 500", ticker="VOO", exchange="NYSEARCA", asset_type=etf)
    qqq = Asset(name="Invesco QQQ", ticker="QQQ", exchange="NASDAQ", asset_type=etf)
    db.add_all([user, brokerage, ira, voo, qqq])
    await db.flush()
    return SimpleNamespace(user=user, brokerage=brokerage, ira=ira, voo=voo, qqq=qqq)


@pytest.fixture
def make_holding(setup):
    """Build a valid VOO holding in the Brokerage account; keyword arguments override any field."""

    def _make_holding(**overrides) -> Holding:
        fields = dict(
            account_id=setup.brokerage.account_id,
            asset_id=setup.voo.asset_id,
            quantity=Decimal("10"),
            avg_price=Decimal("500"),
            first_transaction_timestamp=FIRST_TS,
            last_transaction_timestamp=LAST_TS,
        )
        fields.update(overrides)
        return Holding(**fields)

    return _make_holding


async def _save(db: AsyncSession, holding: Holding) -> Holding:
    db.add(holding)
    await db.flush()
    # holding_id and last_update_timestamp are filled in by Postgres, so read the row back.
    await db.refresh(holding)
    return holding


# Values filled in by the database


async def test_holding_gets_generated_id_and_update_timestamp(db, make_holding):
    holding = await _save(db, make_holding())
    assert isinstance(holding.holding_id, int)
    assert holding.last_update_timestamp is not None


async def test_update_refreshes_last_update_timestamp(db, make_holding):
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)
    holding = await _save(db, make_holding(last_update_timestamp=stale))
    assert holding.last_update_timestamp == stale

    holding.quantity = Decimal("12")
    await db.flush()
    await db.refresh(holding)

    # now() is fixed for the whole test transaction, so compare against it rather than the clock.
    db_now = await db.scalar(select(func.now()))
    assert holding.last_update_timestamp == db_now


async def test_decimal_values_round_trip_exactly(db, make_holding):
    holding = await _save(db, make_holding(quantity=Decimal("0.12345678"), avg_price=Decimal("123456789012.87654321")))
    assert holding.quantity == Decimal("0.12345678")
    assert holding.avg_price == Decimal("123456789012.87654321")


async def test_fully_sold_holding_can_have_zero_quantity(db, make_holding):
    holding = await _save(db, make_holding(quantity=Decimal("0")))
    assert holding.quantity == Decimal("0")


async def test_first_and_last_transaction_can_be_the_same(db, make_holding):
    holding = await _save(db, make_holding(first_transaction_timestamp=LAST_TS))
    assert holding.first_transaction_timestamp == holding.last_transaction_timestamp


# One holding per asset per account


async def test_same_asset_can_be_held_in_different_accounts(db, setup, make_holding):
    await _save(db, make_holding())
    await _save(db, make_holding(account_id=setup.ira.account_id))
    count = await db.scalar(select(func.count()).select_from(Holding).where(Holding.asset_id == setup.voo.asset_id))
    assert count == 2


async def test_account_can_hold_several_assets(db, setup, make_holding):
    await _save(db, make_holding())
    await _save(db, make_holding(asset_id=setup.qqq.asset_id))
    count = await db.scalar(
        select(func.count()).select_from(Holding).where(Holding.account_id == setup.brokerage.account_id)
    )
    assert count == 2


async def test_duplicate_asset_in_same_account_is_rejected(db, make_holding, rejected_by):
    await _save(db, make_holding())
    async with rejected_by("uq_folio_holdings_account_id_asset_id"):
        db.add(make_holding(quantity=Decimal("1")))


# Relationships


async def test_account_loads_its_holdings(db, setup, make_holding):
    await _save(db, make_holding())
    await _save(db, make_holding(asset_id=setup.qqq.asset_id))
    account_id = setup.brokerage.account_id
    db.expunge_all()
    account = (
        await db.scalars(
            select(Account)
            .where(Account.account_id == account_id)
            .options(selectinload(Account.holdings).selectinload(Holding.asset))
        )
    ).one()
    assert sorted(h.asset.ticker for h in account.holdings) == ["QQQ", "VOO"]


async def test_asset_loads_its_holdings(db, setup, make_holding):
    await _save(db, make_holding())
    await _save(db, make_holding(account_id=setup.ira.account_id))
    asset_id = setup.voo.asset_id
    db.expunge_all()
    asset = (
        await db.scalars(
            select(Asset)
            .where(Asset.asset_id == asset_id)
            .options(selectinload(Asset.holdings).selectinload(Holding.account))
        )
    ).one()
    assert sorted(h.account.account_name for h in asset.holdings) == ["Brokerage", "Roth IRA"]


async def test_lazy_loading_holdings_is_blocked(db, setup, make_holding):
    await _save(db, make_holding())
    account_id = setup.brokerage.account_id
    db.expunge_all()
    account = (await db.scalars(select(Account).where(Account.account_id == account_id))).one()
    with pytest.raises(InvalidRequestError):
        _ = account.holdings


# Rules enforced by Postgres


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        pytest.param(dict(quantity=Decimal("-1")), "ck_folio_holdings_quantity_non_negative", id="negative-quantity"),
        pytest.param(dict(avg_price=Decimal("-0.01")), "ck_folio_holdings_avg_price_non_negative", id="negative-avg-price"),
        pytest.param(
            dict(first_transaction_timestamp=LAST_TS + timedelta(seconds=1)),
            "ck_folio_holdings_first_transaction_before_last",
            id="first-after-last",
        ),
        pytest.param(dict(asset_id=999_999), "fk_folio_holdings_asset_id_folio_assets", id="unknown-asset"),
        pytest.param(
            dict(account_id=uuid.UUID(int=0)),
            "fk_folio_holdings_account_id_folio_accounts",
            id="unknown-account",
        ),
        pytest.param(dict(quantity=None), "quantity", id="missing-quantity"),
        pytest.param(dict(avg_price=None), "avg_price", id="missing-avg-price"),
        pytest.param(dict(first_transaction_timestamp=None), "first_transaction_timestamp", id="missing-first-ts"),
        pytest.param(dict(last_transaction_timestamp=None), "last_transaction_timestamp", id="missing-last-ts"),
    ],
)
async def test_invalid_holding_is_rejected(db, make_holding, rejected_by, overrides, constraint):
    async with rejected_by(constraint):
        db.add(make_holding(**overrides))


async def test_account_with_a_holding_cannot_be_deleted(db, setup, make_holding, rejected_by):
    await _save(db, make_holding())
    async with rejected_by("fk_folio_holdings_account_id_folio_accounts"):
        await db.execute(delete(Account).where(Account.account_id == setup.brokerage.account_id))


async def test_asset_with_a_holding_cannot_be_deleted(db, setup, make_holding, rejected_by):
    await _save(db, make_holding())
    async with rejected_by("fk_folio_holdings_asset_id_folio_assets"):
        await db.execute(delete(Asset).where(Asset.asset_id == setup.voo.asset_id))
