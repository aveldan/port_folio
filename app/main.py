import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.config import get_settings
from app.db.migrations import downgrade_to_base, upgrade_to_head


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # migrations/env.py calls asyncio.run(), which can't run inside uvicorn's event loop,
    # so migrations run in a worker thread.
    if settings.run_migrations_on_startup:
        await asyncio.to_thread(upgrade_to_head)
    yield
    if settings.drop_db_on_shutdown:
        await asyncio.to_thread(downgrade_to_base)


app = FastAPI(title="port_folio", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(api_router)
