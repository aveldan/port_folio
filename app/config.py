from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from the environment with the project's .env as a fallback."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30
    # Meant for local development; deployments should run `alembic upgrade head` as a separate step.
    run_migrations_on_startup: bool = False
    # Local development only: drops every table, and all data in them, when the server stops.
    drop_db_on_shutdown: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()