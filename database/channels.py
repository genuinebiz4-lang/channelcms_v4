"""Channel persistence layer for Flowza v1.0."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from database.db import get_connection


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a database row to a dictionary."""
    if row is None:
        return {}
    return dict(row)


def _initialize_sync() -> None:
    """Create the channels table if it does not already exist."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER UNIQUE NOT NULL,
                title TEXT NOT NULL,
                username TEXT,
                invite_link TEXT,
                description TEXT,
                member_count INTEGER DEFAULT 0,
                is_default INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


async def initialize() -> None:
    """Initialize the channels table asynchronously."""
    await asyncio.to_thread(_initialize_sync)


async def add_channel(
    channel_id: int,
    title: str | None,
    username: str | None = None,
    invite_link: str | None = None,
    description: str | None = None,
    member_count: int = 0,
    is_default: int = 0,
) -> dict[str, Any] | None:
    """Persist a new channel record."""
    if not channel_id:
        return None

    def _add() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO channels (
                    channel_id, title, username, invite_link, description, member_count, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_id,
                    title or "Unnamed Channel",
                    username,
                    invite_link,
                    description,
                    member_count,
                    is_default,
                ),
            )
            connection.commit()
            return {
                "id": cursor.lastrowid,
                "channel_id": channel_id,
                "title": title or "Unnamed Channel",
                "username": username,
                "invite_link": invite_link,
                "description": description,
                "member_count": member_count,
                "is_default": is_default,
            }

    try:
        return await asyncio.to_thread(_add)
    except Exception:
        return None


async def delete_channel(channel_id: int) -> bool:
    """Delete a channel from the database."""

    def _delete() -> int:
        with get_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM channels WHERE channel_id = ?",
                (channel_id,),
            )
            return cursor.rowcount

    return bool(await asyncio.to_thread(_delete))


async def update_channel(
    channel_id: int,
    *,
    title: str | None = None,
    username: str | None = None,
    invite_link: str | None = None,
    description: str | None = None,
    member_count: int | None = None,
) -> bool:
    """Update an existing channel record."""

    def _update() -> int:
        with get_connection() as connection:
            query_parts = ["UPDATE channels SET"]
            values: list[Any] = []
            if title is not None:
                query_parts.append("title = ?")
                values.append(title)
            if username is not None:
                query_parts.append("username = ?")
                values.append(username)
            if invite_link is not None:
                query_parts.append("invite_link = ?")
                values.append(invite_link)
            if description is not None:
                query_parts.append("description = ?")
                values.append(description)
            if member_count is not None:
                query_parts.append("member_count = ?")
                values.append(member_count)
            query_parts.append("WHERE channel_id = ?")
            values.append(channel_id)
            cursor = connection.execute(" ".join(query_parts), tuple(values))
            connection.commit()
            return cursor.rowcount

    return bool(await asyncio.to_thread(_update))


async def channel_exists(channel_id: int) -> bool:
    """Return True when a channel has already been saved."""

    def _exists() -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM channels WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            return row is not None

    return await asyncio.to_thread(_exists)


async def get_channel(channel_id: int) -> dict[str, Any] | None:
    """Load a single channel record by Telegram channel id."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM channels WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def get_channels() -> list[dict[str, Any]]:
    """Return all saved channels sorted by title and id."""

    def _get_all() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM channels ORDER BY title COLLATE NOCASE ASC, id ASC"
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_get_all)


async def set_default_channel(channel_id: int) -> bool:
    """Set a single channel as the default channel."""

    def _set_default() -> bool:
        with get_connection() as connection:
            connection.execute("UPDATE channels SET is_default = 0")
            cursor = connection.execute(
                "UPDATE channels SET is_default = 1 WHERE channel_id = ?",
                (channel_id,),
            )
            connection.commit()
            return cursor.rowcount > 0

    return await asyncio.to_thread(_set_default)


async def get_default_channel() -> dict[str, Any] | None:
    """Return the current default channel, if any."""

    def _get_default() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM channels WHERE is_default = 1 LIMIT 1"
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get_default)


async def total_channels() -> int:
    """Return the total number of saved channels."""

    def _count() -> int:
        with get_connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM channels").fetchone()
            return int(row["count"]) if row else 0

    return await asyncio.to_thread(_count)


async def clear_default() -> None:
    """Clear the default marker from all channels."""

    def _clear() -> None:
        with get_connection() as connection:
            connection.execute("UPDATE channels SET is_default = 0")
            connection.commit()

    await asyncio.to_thread(_clear)
