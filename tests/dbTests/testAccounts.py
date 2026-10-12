"""Database tests for the Account model and its links to users and transactions."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Account, Asset, AssetType, Transaction, TransactionSide, User, account_users

pytestmark = pytest.mark.anyio

TS = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
async def setup(db: AsyncSession) -> SimpleNamespace:
    """Users A and B share a joint Brokerage. A also has a Roth IRA, and B has a solo Savings account.

    The joint Brokerage and the Roth IRA have one trade each; Savings has none.
    """
    a, b = User(full_name="User A"), User(full_name="User B")
    joint = Account(users=[a, b], account_name="Brokerage")
    ira = Account(users=[a], account_name="Roth IRA")
    savings = Account(users=[b], account_name="Savings")
    voo = Asset(name="Vanguard S&P 500", ticker="VOO", exchange="NYSEARCA", asset_type=AssetType(name="ETF"))
    db.add_all([a, b, joint, ira, savings, voo])
    await db.flush()
    db.add_all(
        [
            Transaction(account_id=joint.account_id, asset_id=voo.asset_id, timestamp=TS,
                        transaction_side=TransactionSide.BUY, quantity=Decimal(2), price_per_count=Decimal(500)),
            Transaction(account_id=ira.account_id, asset_id=voo.asset_id, timestamp=TS,
                        transaction_side=TransactionSide.BUY, quantity=Decimal(1), price_per_count=Decimal(510)),
        ]
    )
    await db.flush()
    return SimpleNamespace(a=a, b=b, joint=joint, ira=ira, savings=savings, voo=voo)


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    db.expunge_all()
    return (
        await db.scalars(select(User).where(User.user_id == user_id).options(selectinload(User.accounts)))
    ).one()


async def _load_account(db: AsyncSession, account_id: uuid.UUID) -> Account:
    db.expunge_all()
    return (
        await db.scalars(select(Account).where(Account.account_id == account_id).options(selectinload(Account.users)))
    ).one()


async def _member_count(db: AsyncSession, account_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count()).select_from(account_users).where(account_users.c.account_id == account_id)
    )


# Basics


async def test_account_gets_generated_id_and_created_timestamp(db, setup):
    await db.refresh(setup.joint)
    assert isinstance(setup.joint.account_id, uuid.UUID)
    assert setup.joint.created_timestamp is not None


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


async def test_lazy_loading_account_users_is_blocked(db, setup):
    account_id = setup.joint.account_id
    db.expunge_all()
    account = (await db.scalars(select(Account).where(Account.account_id == account_id))).one()
    with pytest.raises(InvalidRequestError):
        _ = account.users


# Shared accounts


async def test_shared_account_lists_all_its_users(db, setup):
    account = await _load_account(db, setup.joint.account_id)
    assert sorted(u.full_name for u in account.users) == ["User A", "User B"]


async def test_each_user_sees_the_shared_account(db, setup):
    joint_id = setup.joint.account_id
    a = await _load_user(db, setup.a.user_id)
    assert {acct.account_name for acct in a.accounts} == {"Brokerage", "Roth IRA"}
    b = await _load_user(db, setup.b.user_id)
    assert {acct.account_name for acct in b.accounts} == {"Brokerage", "Savings"}
    assert joint_id in {acct.account_id for acct in a.accounts} & {acct.account_id for acct in b.accounts}


async def test_user_can_be_added_to_an_existing_account(db, setup):
    await db.execute(insert(account_users).values(account_id=setup.ira.account_id, user_id=setup.b.user_id))
    account = await _load_account(db, setup.ira.account_id)
    assert sorted(u.full_name for u in account.users) == ["User A", "User B"]


async def test_membership_records_when_the_user_was_added(db, setup):
    added = await db.scalar(
        select(account_users.c.added_timestamp).where(
            account_users.c.account_id == setup.joint.account_id, account_users.c.user_id == setup.a.user_id
        )
    )
    assert added is not None


async def test_user_cannot_be_added_to_the_same_account_twice(db, setup, rejected_by):
    async with rejected_by("pk_folio_account_users"):
        await db.execute(insert(account_users).values(account_id=setup.joint.account_id, user_id=setup.a.user_id))


async def test_removing_one_user_keeps_the_account_for_the_other(db, setup):
    joint_id, b_id = setup.joint.account_id, setup.b.user_id
    account = await _load_account(db, joint_id)
    account.users = [u for u in account.users if u.user_id != b_id]
    await db.flush()

    account = await _load_account(db, joint_id)
    assert [u.full_name for u in account.users] == ["User A"]
    b = await _load_user(db, b_id)
    assert [acct.account_name for acct in b.accounts] == ["Savings"]


async def test_account_names_do_not_have_to_be_unique(db, setup):
    db.add(Account(users=[setup.a], account_name="Brokerage"))
    await db.flush()
    count = await db.scalar(select(func.count()).select_from(Account).where(Account.account_name == "Brokerage"))
    assert count == 2


# Deleting


async def test_deleting_an_account_removes_its_memberships(db, setup):
    savings_id = setup.savings.account_id
    assert await _member_count(db, savings_id) == 1
    await db.execute(delete(Account).where(Account.account_id == savings_id))
    assert await _member_count(db, savings_id) == 0


async def test_account_with_transactions_cannot_be_deleted(db, setup, rejected_by):
    async with rejected_by("fk_folio_transactions_account_id_folio_accounts"):
        await db.execute(delete(Account).where(Account.account_id == setup.joint.account_id))


async def test_user_still_on_an_account_cannot_be_deleted(db, setup, rejected_by):
    async with rejected_by("fk_folio_account_users_user_id_folio_users"):
        await db.execute(delete(User).where(User.user_id == setup.b.user_id))


async def test_user_with_no_accounts_can_be_deleted(db):
    user = User(full_name="User C")
    db.add(user)
    await db.flush()
    await db.execute(delete(User).where(User.user_id == user.user_id))
    assert await db.scalar(select(func.count()).select_from(User).where(User.user_id == user.user_id)) == 0


# Rules enforced by Postgres


async def test_transaction_requires_an_account(db, setup, rejected_by):
    async with rejected_by('column "account_id"'):
        db.add(Transaction(asset_id=setup.voo.asset_id, timestamp=TS, transaction_side=TransactionSide.BUY,
                           quantity=Decimal(1), price_per_count=Decimal(1)))


@pytest.mark.parametrize(
    ("member", "constraint"),
    [
        pytest.param("unknown-user", "fk_folio_account_users_user_id_folio_users", id="unknown-user"),
        pytest.param("unknown-account", "fk_folio_account_users_account_id_folio_accounts", id="unknown-account"),
    ],
)
async def test_membership_must_point_at_real_rows(db, setup, rejected_by, member, constraint):
    values = dict(account_id=setup.joint.account_id, user_id=setup.a.user_id)
    values["user_id" if member == "unknown-user" else "account_id"] = uuid.UUID(int=0)
    async with rejected_by(constraint):
        await db.execute(insert(account_users).values(**values))
