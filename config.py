"""Application configuration for Flowza v1.0."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

APP_NAME = "Flowza"
APP_TITLE = "Flowza v1.0"
VERSION = "Flowza v1.0.2"


def _get_int_env(name: str, default: int = 0) -> int:
    """Safely parse an integer environment variable."""
    value = os.getenv(name, "")
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = _get_int_env("OWNER_ID", 0)
DATABASE = os.getenv("DATABASE", "database/data/channelcms.db").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata").strip()


def get_database_path() -> str:
    """Resolve the SQLite database path from the environment."""
    if os.path.isabs(DATABASE):
        return DATABASE
    return str(BASE_DIR / DATABASE)


DATABASE_PATH = get_database_path()