"""Database tests for the Account model and its links to users and transactions."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Account, Asset, AssetType, Transaction, TransactionSide, User

pytestmark = pytest.mark.anyio

TS = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
async def setup(db: AsyncSession) -> SimpleNamespace:
    """User A has a Brokerage and a Roth IRA account with one trade each; user B has a Brokerage."""
    a, b = User(full_name="User A"), User(full_name="User B")
    brokerage = Account(user=a, account_name="Brokerage")
    ira = Account(user=a, account_name="Roth IRA")
    b_brokerage = Account(user=b, account_name="Brokerage")
    voo = Asset(name="Vanguard S&P 500", ticker="VOO", exchange="NYSEARCA", asset_type=AssetType(name="ETF"))
    db.add_all([a, b, brokerage, ira, b_brokerage, voo])
    await db.flush()
    db.add_all(
        [
            Transaction(account_id=brokerage.account_id, asset_id=voo.asset_id, timestamp=TS,
                        transaction_side=TransactionSide.BUY, quantity=Decimal(2), price_per_count=Decimal(500)),
            Transaction(account_id=ira.account_id, asset_id=voo.asset_id, timestamp=TS,
                        transaction_side=TransactionSide.BUY, quantity=Decimal(1), price_per_count=Decimal(510)),
        ]
    )
    await db.flush()
    return SimpleNamespace(a=a, b=b, brokerage=brokerage, ira=ira, b_brokerage=b_brokerage, voo=voo)


async def test_account_gets_generated_id_and_created_timestamp(db, setup):
    await db.refresh(setup.brokerage)
    assert isinstance(setup.brokerage.account_id, uuid.UUID)
    assert setup.brokerage.created_timestamp is not None


async def test_user_loads_accounts_with_their_transactions(db, setup):
    user_id = setup.a.user_id
    db.expunge_all()
    user = (
        await db.scalars(
            select(User)
            .where(User.user_id == user_id)
            .options(selectinload(User.accounts).selectinload(Account.transactions))
        )
    ).one()
    assert {acct.account_name: len(acct.transactions) for acct in user.accounts} == {"Brokerage": 1, "Roth IRA": 1}


async def test_same_account_name_allowed_for_different_users(setup):
    assert setup.brokerage.account_name == setup.b_brokerage.account_name
    assert setup.brokerage.user_id != setup.b_brokerage.user_id


async def test_duplicate_account_name_for_same_user_rejected(db, setup, rejected_by):
    async with rejected_by("uq_folio_accounts_user_id_account_name"):
        db.add(Account(user_id=setup.a.user_id, account_name="Brokerage"))


async def test_transaction_requires_an_account(db, setup, rejected_by):
    async with rejected_by('column "account_id"'):
        db.add(Transaction(asset_id=setup.voo.asset_id, timestamp=TS, transaction_side=TransactionSide.BUY,
                           quantity=Decimal(1), price_per_count=Decimal(1)))


async def test_account_with_transactions_cannot_be_deleted(db, setup, rejected_by):
    async with rejected_by("fk_folio_transactions_account_id_folio_accounts"):
        await db.execute(delete(Account).where(Account.account_id == setup.brokerage.account_id))


async def test_user_with_accounts_cannot_be_deleted(db, setup, rejected_by):
    async with rejected_by("fk_folio_accounts_user_id_folio_users"):
        await db.execute(delete(User).where(User.user_id == setup.b.user_id))
