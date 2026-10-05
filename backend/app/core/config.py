"""Environment-driven configuration. Everything has a development default."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "fintechco.db"

# Fixed development key. Override with FINTECHCO_SESSION_SECRET outside development.
_DEV_SESSION_SECRET = "fintechco-business-development-session-key"


def db_path() -> Path:
    """Path of the SQLite database, resolved from the package location, never the cwd."""
    raw = os.environ.get("FINTECHCO_DB_PATH")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_DB_PATH


def env_name() -> str:
    return os.environ.get("FINTECHCO_ENV", "development").strip().lower()


def is_development() -> bool:
    return env_name() != "production"


def session_secret() -> bytes:
    return os.environ.get("FINTECHCO_SESSION_SECRET", _DEV_SESSION_SECRET).encode("utf-8")
