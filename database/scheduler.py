"""Scheduler persistence for Flowza v1.0."""

from __future__ import annotations

import asyncio
from typing import Any

from database.db import get_connection


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a database row to a dictionary."""
    if row is None:
        return {}
    return dict(row)


def _initialize_sync() -> None:
    """Create the scheduled_posts table if it does not already exist."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id INTEGER,
                channel_id INTEGER,
                schedule_type TEXT,
                schedule_date TEXT,
                schedule_time TEXT,
                cron_expression TEXT,
                timezone TEXT DEFAULT 'Asia/Kolkata',
                status TEXT DEFAULT 'pending',
                last_run TEXT,
                next_run TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


async def initialize() -> None:
    """Initialize the scheduler table asynchronously."""
    await asyncio.to_thread(_initialize_sync)


async def add_schedule(
    *,
    draft_id: int,
    channel_id: int,
    schedule_type: str,
    schedule_date: str | None = None,
    schedule_time: str | None = None,
    cron_expression: str | None = None,
    timezone: str = "Asia/Kolkata",
    status: str = "pending",
    next_run: str | None = None,
) -> dict[str, Any] | None:
    """Persist a scheduled post entry."""

    def _add() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scheduled_posts (
                    draft_id, channel_id, schedule_type, schedule_date, schedule_time,
                    cron_expression, timezone, status, next_run
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    channel_id,
                    schedule_type,
                    schedule_date,
                    schedule_time,
                    cron_expression,
                    timezone,
                    status,
                    next_run,
                ),
            )
            connection.commit()
            return {
                "id": cursor.lastrowid,
                "draft_id": draft_id,
                "channel_id": channel_id,
                "schedule_type": schedule_type,
                "schedule_date": schedule_date,
                "schedule_time": schedule_time,
                "cron_expression": cron_expression,
                "timezone": timezone,
                "status": status,
                "next_run": next_run,
            }

    return await asyncio.to_thread(_add)


async def update_schedule(schedule_id: int, **fields: Any) -> bool:
    """Update an existing scheduled post."""

    def _update() -> int:
        with get_connection() as connection:
            if not fields:
                return 0
            assignments = [f"{key} = ?" for key in fields]
            values = list(fields.values())
            values.append(schedule_id)
            cursor = connection.execute(
                f"UPDATE scheduled_posts SET {', '.join(assignments)} WHERE id = ?",
                tuple(values),
            )
            connection.commit()
            return cursor.rowcount

    return bool(await asyncio.to_thread(_update))


async def delete_schedule(schedule_id: int) -> bool:
    """Delete a scheduled post entry."""

    def _delete() -> int:
        with get_connection() as connection:
            cursor = connection.execute("DELETE FROM scheduled_posts WHERE id = ?", (schedule_id,))
            connection.commit()
            return cursor.rowcount

    return bool(await asyncio.to_thread(_delete))


async def get_schedule(schedule_id: int) -> dict[str, Any] | None:
    """Fetch a single scheduled post."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM scheduled_posts WHERE id = ?",
                (schedule_id,),
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def get_all_schedules() -> list[dict[str, Any]]:
    """Return all scheduled posts ordered by next run."""

    def _get_all() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM scheduled_posts ORDER BY id DESC"
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_get_all)


async def get_pending() -> list[dict[str, Any]]:
    """Return pending or active scheduled posts."""

    def _get_pending() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM scheduled_posts WHERE status IN ('pending', 'active') ORDER BY id DESC"
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_get_pending)


async def find_duplicate_schedule(
    *,
    draft_id: int,
    channel_id: int,
    schedule_type: str,
    schedule_date: str | None,
    schedule_time: str | None,
) -> dict[str, Any] | None:
    """Return an existing active/pending schedule matching the same payload."""

    def _find() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM scheduled_posts
                WHERE draft_id = ?
                  AND channel_id = ?
                  AND schedule_type = ?
                  AND COALESCE(schedule_date, '') = COALESCE(?, '')
                  AND COALESCE(schedule_time, '') = COALESCE(?, '')
                  AND status IN ('pending', 'active', 'paused')
                ORDER BY id DESC
                LIMIT 1
                """,
                (draft_id, channel_id, schedule_type, schedule_date, schedule_time),
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_find)


async def mark_completed(schedule_id: int) -> bool:
    """Mark a schedule as completed."""
    return await update_schedule(schedule_id, status="completed", last_run="now")


async def pause_schedule(schedule_id: int) -> bool:
    """Pause a schedule."""
    return await update_schedule(schedule_id, status="paused")


async def resume_schedule(schedule_id: int) -> bool:
    """Resume a schedule."""
    return await update_schedule(schedule_id, status="pending")
