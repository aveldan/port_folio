"""Database tests for the Transaction model."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Account, Asset, AssetType, Transaction, TransactionSide, User

pytestmark = pytest.mark.anyio

TS = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
async def setup(db: AsyncSession) -> SimpleNamespace:
    """A user with one account, and one ETF to trade."""
    user = User(full_name="Test User")
    account = Account(users=[user], account_name="Brokerage")
    voo = Asset(name="Vanguard S&P 500", ticker="VOO", exchange="NYSEARCA", asset_type=AssetType(name="ETF"))
    db.add_all([user, account, voo])
    await db.flush()
    return SimpleNamespace(user=user, account=account, voo=voo)


@pytest.fixture
def make_trade(setup):
    """Build a valid trade in the test account; keyword arguments override any field."""

    def _make_trade(**overrides) -> Transaction:
        fields = dict(
            account_id=setup.account.account_id,
            asset_id=setup.voo.asset_id,
            timestamp=TS,
            transaction_side=TransactionSide.BUY,
            quantity=Decimal("1"),
            price_per_count=Decimal("1"),
        )
        fields.update(overrides)
        return Transaction(**fields)

    return _make_trade


async def _save(db: AsyncSession, trade: Transaction) -> Transaction:
    db.add(trade)
    await db.flush()
    # total_price is computed by Postgres, so read the row back.
    await db.refresh(trade)
    return trade


# total_price is calculated by the database


async def test_buy_total_adds_commission(db, make_trade):
    trade = await _save(db, make_trade(quantity=Decimal("2.5"), price_per_count=Decimal("500.10"), commission=Decimal("1")))
    assert trade.total_price == Decimal("1251.25")


async def test_sell_total_subtracts_commission(db, make_trade):
    trade = await _save(db, make_trade(transaction_side=TransactionSide.SELL, quantity=Decimal("1"),
                                       price_per_count=Decimal("520"), commission=Decimal("1")))
    assert trade.total_price == Decimal("519")


async def test_commission_defaults_to_zero(db, make_trade):
    trade = await _save(db, make_trade(quantity=Decimal("1"), price_per_count=Decimal("100")))
    assert trade.commission == Decimal("0")
    assert trade.total_price == Decimal("100")


async def test_side_is_read_back_as_enum(db, make_trade):
    trade = await _save(db, make_trade(transaction_side=TransactionSide.SELL))
    assert trade.transaction_side is TransactionSide.SELL


# Relationships


async def test_lazy_loading_transactions_is_blocked(db, setup, make_trade):
    await _save(db, make_trade())
    asset_id = setup.voo.asset_id
    db.expunge_all()
    asset = (await db.scalars(select(Asset).where(Asset.asset_id == asset_id))).one()
    with pytest.raises(InvalidRequestError):
        _ = asset.transactions


async def test_selectinload_loads_transactions(db, setup, make_trade):
    for _ in range(3):
        await _save(db, make_trade())
    asset_id = setup.voo.asset_id
    db.expunge_all()
    asset = (
        await db.scalars(select(Asset).where(Asset.asset_id == asset_id).options(selectinload(Asset.transactions)))
    ).one()
    assert len(asset.transactions) == 3


async def test_trade_links_to_its_account(db, make_trade):
    trade = await _save(db, make_trade())
    db.expunge_all()
    loaded = (
        await db.scalars(
            select(Transaction)
            .where(Transaction.transaction_id == trade.transaction_id)
            .options(selectinload(Transaction.account))
        )
    ).one()
    assert loaded.account.account_name == "Brokerage"


# Rules enforced by Postgres


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        pytest.param(dict(quantity=Decimal("-1")), "ck_folio_transactions_quantity_positive", id="negative-quantity"),
        pytest.param(dict(quantity=Decimal("0")), "ck_folio_transactions_quantity_positive", id="zero-quantity"),
        pytest.param(dict(price_per_count=Decimal("-1")), "ck_folio_transactions_price_non_negative", id="negative-price"),
        pytest.param(dict(commission=Decimal("-1")), "ck_folio_transactions_commission_non_negative", id="negative-commission"),
        pytest.param(dict(asset_id=999_999), "fk_folio_transactions_asset_id_folio_assets", id="unknown-asset"),
    ],
)
async def test_invalid_trade_is_rejected(db, make_trade, rejected_by, overrides, constraint):
    async with rejected_by(constraint):
        db.add(make_trade(**overrides))
