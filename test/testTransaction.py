import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, inspect
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import selectinload
from app.db.base import Base
from app.db.models import Asset, AssetType, Transaction, TransactionSide

url = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l)["DATABASE_URL"]

async def main():
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        print("existing tables:", await conn.run_sync(lambda c: inspect(c).get_table_names()))
        await conn.rollback()
        trans = await conn.begin()
        await conn.run_sync(Base.metadata.create_all)
        s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        etf = AssetType(name="ETF")
        voo = Asset(name="Vanguard S&P 500", ticker="VOO", exchange="NYSEARCA", asset_type=etf)
        s.add_all([etf, voo]); await s.flush()
        ts = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)
        buy = Transaction(asset_id=voo.asset_id, timestamp=ts, transaction_side=TransactionSide.BUY,
                          quantity=Decimal("2.5"), price_per_count=Decimal("500.10"), commission=Decimal("1"))
        sell = Transaction(asset_id=voo.asset_id, timestamp=ts, transaction_side=TransactionSide.SELL,
                           quantity=Decimal("1"), price_per_count=Decimal("520"), commission=Decimal("1"))
        nocomm = Transaction(asset_id=voo.asset_id, timestamp=ts, transaction_side=TransactionSide.BUY,
                             quantity=Decimal("1"), price_per_count=Decimal("100"))
        s.add_all([buy, sell, nocomm]); await s.flush()
        for t in (buy, sell, nocomm): await s.refresh(t)
        print("buy total:", buy.total_price, "| sell total:", sell.total_price, "| no-commission total:", nocomm.total_price)
        print("side read back:", repr(buy.transaction_side))
        try:
            _ = voo.transactions
            print("lazy load NOT blocked")
        except InvalidRequestError as e:
            print("lazy load blocked as expected:", type(e).__name__)
        s.expunge_all()
        a = (await s.scalars(select(Asset).options(selectinload(Asset.transactions)).where(Asset.ticker == "VOO"))).one()
        print("selectinload count:", len(a.transactions))
        for label, kw in [("negative quantity", dict(quantity=Decimal("-1"))), ("bad asset_id", dict(asset_id=999999))]:
            try:
                async with s.begin_nested():
                    base = dict(asset_id=a.asset_id, timestamp=ts, transaction_side=TransactionSide.BUY,
                                quantity=Decimal("1"), price_per_count=Decimal("1")); base.update(kw)
                    s.add(Transaction(**base)); await s.flush()
                print(label, "-> NOT rejected")
            except IntegrityError as e:
                print(label, "-> rejected:", str(e.orig).split("\n")[0][-80:])
        await s.close()
        await trans.rollback()
        print("tables after rollback:", await conn.run_sync(lambda c: inspect(c).get_table_names()))
    await engine.dispose()

asyncio.run(main())