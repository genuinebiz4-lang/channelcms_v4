"""Draft persistence for Flowza v1.0."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from database.db import get_connection


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a database row into a dictionary."""
    if row is None:
        return {}
    return dict(row)


def _initialize_sync() -> None:
    """Create the drafts table if it does not already exist and align its schema."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_type TEXT NOT NULL,
                text TEXT,
                file_id TEXT,
                caption TEXT,
                album TEXT,
                parse_mode TEXT DEFAULT 'HTML',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(drafts)")}
        if "draft_type" not in columns:
            connection.execute("ALTER TABLE drafts ADD COLUMN draft_type TEXT NOT NULL DEFAULT 'text'")
        if "text" not in columns:
            connection.execute("ALTER TABLE drafts ADD COLUMN text TEXT")
        if "file_id" not in columns:
            connection.execute("ALTER TABLE drafts ADD COLUMN file_id TEXT")
        if "caption" not in columns:
            connection.execute("ALTER TABLE drafts ADD COLUMN caption TEXT")
        if "album" not in columns:
            connection.execute("ALTER TABLE drafts ADD COLUMN album TEXT")
        if "parse_mode" not in columns:
            connection.execute("ALTER TABLE drafts ADD COLUMN parse_mode TEXT DEFAULT 'HTML'")
        if "created_at" not in columns:
            connection.execute("ALTER TABLE drafts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        connection.execute("UPDATE drafts SET draft_type = 'text' WHERE draft_type IS NULL OR draft_type = ''")
        connection.commit()


async def initialize() -> None:
    """Initialize the drafts table asynchronously."""
    await asyncio.to_thread(_initialize_sync)


async def clear() -> None:
    """Remove all draft rows."""

    def _clear() -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM drafts")
            connection.commit()

    await asyncio.to_thread(_clear)


async def save_text(text: str, parse_mode: str = "HTML") -> dict[str, Any] | None:
    """Persist a text draft."""

    def _save() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO drafts (draft_type, text, parse_mode) VALUES (?, ?, ?)",
                ("text", text, parse_mode),
            )
            connection.commit()
            return {"id": cursor.lastrowid, "draft_type": "text", "text": text, "parse_mode": parse_mode}

    return await asyncio.to_thread(_save)


async def save_photo(file_id: str, caption: str | None = None, parse_mode: str = "HTML") -> dict[str, Any] | None:
    """Persist a photo draft."""

    def _save() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO drafts (draft_type, file_id, caption, parse_mode) VALUES (?, ?, ?, ?)",
                ("photo", file_id, caption, parse_mode),
            )
            connection.commit()
            return {"id": cursor.lastrowid, "draft_type": "photo", "file_id": file_id, "caption": caption, "parse_mode": parse_mode}

    return await asyncio.to_thread(_save)


async def save_animation(file_id: str, caption: str | None = None, parse_mode: str = "HTML") -> dict[str, Any] | None:
    """Persist an animation draft."""

    def _save() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO drafts (draft_type, file_id, caption, parse_mode) VALUES (?, ?, ?, ?)",
                ("gif", file_id, caption, parse_mode),
            )
            connection.commit()
            return {"id": cursor.lastrowid, "draft_type": "gif", "file_id": file_id, "caption": caption, "parse_mode": parse_mode}

    return await asyncio.to_thread(_save)


async def save_video(file_id: str, caption: str | None = None, parse_mode: str = "HTML") -> dict[str, Any] | None:
    """Persist a video draft."""

    def _save() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO drafts (draft_type, file_id, caption, parse_mode) VALUES (?, ?, ?, ?)",
                ("video", file_id, caption, parse_mode),
            )
            connection.commit()
            return {"id": cursor.lastrowid, "draft_type": "video", "file_id": file_id, "caption": caption, "parse_mode": parse_mode}

    return await asyncio.to_thread(_save)


async def save_document(file_id: str, caption: str | None = None, parse_mode: str = "HTML") -> dict[str, Any] | None:
    """Persist a document draft."""

    def _save() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO drafts (draft_type, file_id, caption, parse_mode) VALUES (?, ?, ?, ?)",
                ("document", file_id, caption, parse_mode),
            )
            connection.commit()
            return {"id": cursor.lastrowid, "draft_type": "document", "file_id": file_id, "caption": caption, "parse_mode": parse_mode}

    return await asyncio.to_thread(_save)


async def save_album(file_ids: list[str], caption: str | None = None, media_group_id: str | None = None, parse_mode: str = "HTML") -> dict[str, Any] | None:
    """Persist an album draft."""

    def _save() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO drafts (draft_type, album, caption, parse_mode) VALUES (?, ?, ?, ?)",
                ("album", json.dumps(file_ids), caption, parse_mode),
            )
            connection.commit()
            return {"id": cursor.lastrowid, "draft_type": "album", "album": json.dumps(file_ids), "caption": caption, "parse_mode": parse_mode}

    return await asyncio.to_thread(_save)


async def get_latest() -> dict[str, Any] | None:
    """Return the most recently created draft."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM drafts ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def get_draft(draft_id: int) -> dict[str, Any] | None:
    """Return a draft by its identifier."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def update_draft(draft_id: int, **fields: Any) -> bool:
    """Update one or more fields on an existing draft."""

    def _update() -> int:
        with get_connection() as connection:
            if not fields:
                return 0
            assignments = ["%s = ?" % key for key in fields]
            values = list(fields.values())
            values.append(draft_id)
            cursor = connection.execute(
                f"UPDATE drafts SET {', '.join(assignments)} WHERE id = ?",
                tuple(values),
            )
            connection.commit()
            return cursor.rowcount

    return bool(await asyncio.to_thread(_update))


async def delete(draft_id: int) -> bool:
    """Delete a draft by id."""

    def _delete() -> int:
        with get_connection() as connection:
            cursor = connection.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
            connection.commit()
            return cursor.rowcount

    return bool(await asyncio.to_thread(_delete))
