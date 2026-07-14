"""Approval queue persistence layer for Flowza v1.0."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from database.db import get_connection

QUEUE_STATUSES = {"pending", "approved", "rejected", "published", "expired", "cancelled"}


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initialize_sync() -> None:
    """Create approval queue table and indexes if absent."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS approval_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id INTEGER NOT NULL,
                editor_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                workspace TEXT NOT NULL,
                destination_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_by INTEGER,
                rejected_by INTEGER,
                rejected_reason TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_approval_queue_admin_status ON approval_queue(admin_id, status);
            CREATE INDEX IF NOT EXISTS idx_approval_queue_editor_status ON approval_queue(editor_id, status);
            CREATE INDEX IF NOT EXISTS idx_approval_queue_draft ON approval_queue(draft_id);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_pending_draft ON approval_queue(draft_id) WHERE status = 'pending';
            """
        )


async def initialize() -> None:
    await asyncio.to_thread(_initialize_sync)


async def create_approval_request(
    *,
    draft_id: int,
    editor_id: int,
    admin_id: int,
    workspace: str,
    destination_id: int | None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Create a pending approval request when eligible."""

    def _create() -> tuple[bool, str, dict[str, Any] | None]:
        with get_connection() as connection:
            draft = connection.execute("SELECT id FROM drafts WHERE id = ?", (draft_id,)).fetchone()
            if draft is None:
                return False, "Draft not found.", None

            pending = connection.execute(
                "SELECT id FROM approval_queue WHERE draft_id = ? AND status = 'pending'",
                (draft_id,),
            ).fetchone()
            if pending is not None:
                return False, "This draft is already pending approval.", None

            now = _now_iso()
            cursor = connection.execute(
                """
                INSERT INTO approval_queue (
                    draft_id, editor_id, admin_id, workspace, destination_id,
                    status, created_at, updated_at, approved_by, rejected_by, rejected_reason
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, NULL, NULL, NULL)
                """,
                (draft_id, editor_id, admin_id, workspace, destination_id, now, now),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM approval_queue WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return True, "Approval request submitted.", None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_create)


async def get_queue_item(queue_id: int) -> dict[str, Any] | None:
    """Get one queue record by id."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,)).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def list_pending_for_admin(admin_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """List pending requests for an admin."""

    safe_limit = max(1, min(100, int(limit)))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM approval_queue
                WHERE admin_id = ? AND status = 'pending'
                ORDER BY id DESC
                LIMIT ?
                """,
                (admin_id, safe_limit),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def list_for_editor(editor_id: int, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List queue records for one editor."""

    safe_limit = max(1, min(200, int(limit)))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if status and status in QUEUE_STATUSES:
                rows = connection.execute(
                    """
                    SELECT * FROM approval_queue
                    WHERE editor_id = ? AND status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (editor_id, status, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM approval_queue
                    WHERE editor_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (editor_id, safe_limit),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def set_status(
    queue_id: int,
    *,
    status: str,
    approved_by: int | None = None,
    rejected_by: int | None = None,
    rejected_reason: str | None = None,
) -> bool:
    """Update queue status and actor metadata."""
    if status not in QUEUE_STATUSES:
        return False

    def _set() -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT id FROM approval_queue WHERE id = ?", (queue_id,)).fetchone()
            if row is None:
                return False
            connection.execute(
                """
                UPDATE approval_queue
                SET status = ?, updated_at = ?, approved_by = ?, rejected_by = ?, rejected_reason = ?
                WHERE id = ?
                """,
                (status, _now_iso(), approved_by, rejected_by, rejected_reason, queue_id),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_set)


async def cancel_for_draft(draft_id: int) -> int:
    """Cancel pending approvals for a deleted draft."""

    def _cancel() -> int:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE approval_queue
                SET status = 'cancelled', updated_at = ?
                WHERE draft_id = ? AND status = 'pending'
                """,
                (_now_iso(), draft_id),
            )
            connection.commit()
            return int(cursor.rowcount)

    return await asyncio.to_thread(_cancel)


async def mark_published_for_draft(draft_id: int, destination_id: int | None = None) -> list[dict[str, Any]]:
    """Mark approved/pending queue rows as published for a draft and return affected rows."""

    def _mark() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if destination_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM approval_queue
                    WHERE draft_id = ? AND status IN ('pending', 'approved')
                    """,
                    (draft_id,),
                ).fetchall()
                connection.execute(
                    """
                    UPDATE approval_queue
                    SET status = 'published', updated_at = ?
                    WHERE draft_id = ? AND status IN ('pending', 'approved')
                    """,
                    (_now_iso(), draft_id),
                )
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM approval_queue
                    WHERE draft_id = ? AND destination_id = ? AND status IN ('pending', 'approved')
                    """,
                    (draft_id, destination_id),
                ).fetchall()
                connection.execute(
                    """
                    UPDATE approval_queue
                    SET status = 'published', updated_at = ?
                    WHERE draft_id = ? AND destination_id = ? AND status IN ('pending', 'approved')
                    """,
                    (_now_iso(), draft_id, destination_id),
                )
            connection.commit()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_mark)


async def get_admin_stats(admin_id: int) -> dict[str, int]:
    """Get approval status counters for one admin."""

    def _stats() -> dict[str, int]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS c
                FROM approval_queue
                WHERE admin_id = ?
                GROUP BY status
                """,
                (admin_id,),
            ).fetchall()
            counters = {"pending": 0, "approved": 0, "rejected": 0, "published": 0, "expired": 0, "cancelled": 0}
            for row in rows:
                counters[str(row["status"])] = int(row["c"])
            return counters

    return await asyncio.to_thread(_stats)


async def get_editor_stats(editor_id: int) -> dict[str, int]:
    """Get approval status counters for one editor."""

    def _stats() -> dict[str, int]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS c
                FROM approval_queue
                WHERE editor_id = ?
                GROUP BY status
                """,
                (editor_id,),
            ).fetchall()
            counters = {"pending": 0, "approved": 0, "rejected": 0, "published": 0, "expired": 0, "cancelled": 0}
            for row in rows:
                counters[str(row["status"])] = int(row["c"])
            return counters

    return await asyncio.to_thread(_stats)


async def get_owner_stats() -> dict[str, int]:
    """Get global approval queue counters for owner dashboard."""

    def _stats() -> dict[str, int]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS c FROM approval_queue GROUP BY status"
            ).fetchall()
            counters = {"pending": 0, "approved": 0, "rejected": 0, "published": 0, "expired": 0, "cancelled": 0}
            for row in rows:
                counters[str(row["status"])] = int(row["c"])
            return counters

    return await asyncio.to_thread(_stats)
