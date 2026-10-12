"""App-wide exception handlers.

Every error the API returns has the same JSON shape:

    {"code": "validation_error", "message": "...", "details": [{"field": "email", "message": "..."}]}

`details` lists one entry per offending field and is empty when the error isn't tied to a field.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.security import InvalidCredentialsError

logger = logging.getLogger(__name__)

NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"

CONSTRAINT_MESSAGES: dict[str, tuple[str | None, str]] = {
    "ix_folio_users_email": ("email", "A user with this email already exists"),
    "ck_folio_users_birth_date_not_in_future": ("birth_date", "birth_date cannot be in the future"),
    "uq_folio_profiles_provider_identifier": ("user_name", "This user name is already taken"),
}

_PYDANTIC_PREFIXES = ("Value error, ", "Assertion failed, ")


def _error(status_code: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "details": details or []},
    )


def _field_path(loc: tuple) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in {"body", "query", "path", "header", "cookie"}:
        parts = parts[1:]
    return ".".join(parts) or "body"


def _clean_message(msg: str) -> str:
    for prefix in _PYDANTIC_PREFIXES:
        if msg.startswith(prefix):
            return msg[len(prefix):]
    return msg


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"field": _field_path(err["loc"]), "message": _clean_message(err["msg"])} for err in exc.errors()]
    return _error(422, "validation_error", "The request contains invalid data", details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    response = _error(exc.status_code, "http_error", message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
    response = _error(401, "invalid_credentials", str(exc) or "Invalid credentials")
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


def _db_error_info(exc: IntegrityError) -> tuple[str | None, str | None]:
    """Return (sqlstate, constraint_name) from the underlying asyncpg error, if available."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    driver_error = getattr(orig, "__cause__", None)
    constraint = getattr(driver_error, "constraint_name", None)
    return sqlstate, constraint


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    sqlstate, constraint = _db_error_info(exc)

    if constraint in CONSTRAINT_MESSAGES:
        field, message = CONSTRAINT_MESSAGES[constraint]
        status_code, code = (409, "conflict") if sqlstate == UNIQUE_VIOLATION else (422, "validation_error")
        details = [{"field": field, "message": message}] if field else []
        return _error(status_code, code, message, details)

    if sqlstate == UNIQUE_VIOLATION:
        return _error(409, "conflict", "A record with these values already exists")
    if sqlstate == FOREIGN_KEY_VIOLATION:
        return _error(409, "conflict", "This references a record that does not exist or is still in use")
    if sqlstate in {CHECK_VIOLATION, NOT_NULL_VIOLATION}:
        return _error(422, "validation_error", "The request contains invalid data")

    logger.exception("Unhandled integrity error", exc_info=exc)
    return _error(500, "internal_error", "An unexpected error occurred")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return _error(500, "internal_error", "An unexpected error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)