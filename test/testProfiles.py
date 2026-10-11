import asyncio
from sqlalchemy import inspect, select, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers, selectinload
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.db.base import Base
from app.db.models import AuthProvider, Profile, User

configure_mappers()
d = postgresql.dialect()
print(CreateTable(Profile.__table__).compile(dialect=d))
for i in Profile.__table__.indexes: print(CreateIndex(i).compile(dialect=d))
url = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l)["DATABASE_URL"]

async def main():
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        print("existing tables:", await conn.run_sync(lambda c: inspect(c).get_table_names()))
        await conn.rollback()
        trans = await conn.begin()
        await conn.run_sync(Base.metadata.create_all)
        s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        u = User(full_name="Test User")
        p1 = Profile(user=u, identifier="Retirement", secret="$argon2id$fake1")
        p2 = Profile(user=u, identifier="trading", secret="$argon2id$fake2")
        p3 = Profile(user=u, provider=AuthProvider.GOOGLE, identifier="109876543210")
        s.add_all([u, p1, p2, p3]); await s.flush(); await s.refresh(p1)
        print("default provider:", repr(p1.provider), "| identifier:", p1.identifier)
        s.expunge_all()
        got = (await s.scalars(select(User).options(selectinload(User.profiles)))).one()
        print("profiles for one user:", sorted(p.identifier for p in got.profiles))
        cases = [
            ("password profile with no secret", lambda: Profile(user_id=got.user_id, identifier="nosecret")),
            ("same username, same provider", lambda: Profile(user_id=got.user_id, identifier="RETIREMENT", secret="x")),
        ]
        for label, mk in cases:
            try:
                async with s.begin_nested():
                    s.add(mk()); await s.flush()
                print(label, "-> NOT rejected")
            except IntegrityError as e:
                print(label, "-> rejected:", str(e.orig).split("\n")[0][-55:])
        async with s.begin_nested():
            s.add(Profile(user_id=got.user_id, provider=AuthProvider.GOOGLE, identifier="trading")); await s.flush()
        print("same identifier, different provider -> allowed")
        await s.execute(delete(User).where(User.user_id == got.user_id))
        print("profiles left after deleting user:", (await s.scalar(select(func.count()).select_from(Profile))))
        await s.close(); await trans.rollback()
        print("tables after rollback:", await conn.run_sync(lambda c: inspect(c).get_table_names()))
    await engine.dispose()
asyncio.run(main())