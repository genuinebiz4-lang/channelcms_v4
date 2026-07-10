"""Database helpers for ChannelCMS V4."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """Create and return a SQLite connection for the application."""
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    """Initialize the core database schema."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def set_setting(key: str, value: Any) -> None:
    """Persist a single application setting."""
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO bot_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        connection.commit()


def get_setting(key: str, default: Any = None) -> Any:
    """Return a persisted application setting."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM bot_settings WHERE key = ?",
            (key,),
        ).fetchone()
    return default if row is None else row["value"]
