from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _config() -> Config:
    config = Config(str(ALEMBIC_INI))
    # Keep uvicorn's logging; see migrations/env.py.
    config.attributes["configure_logger"] = False
    return config


def upgrade_to_head() -> None:
    """Apply every pending Alembic migration, the same as `alembic upgrade head`."""
    command.upgrade(_config(), "head")


def downgrade_to_base() -> None:
    """Undo every migration, dropping all tables and their data, the same as `alembic downgrade base`."""
    command.downgrade(_config(), "base")
