from fastapi import FastAPI

from app.api.errors import register_exception_handlers

app = FastAPI(title="port_folio")
register_exception_handlers(app)
