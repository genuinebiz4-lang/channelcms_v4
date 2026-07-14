"""Enterprise scheduler, analytics, notifications, audit, and search persistence for Flowza v1.0.2."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from database.db import get_connection


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initialize_sync() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS retry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER,
                draft_id INTEGER,
                channel_id INTEGER,
                workspace_id INTEGER,
                retry_reason TEXT,
                priority INTEGER NOT NULL DEFAULT 5,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS publish_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id INTEGER,
                channel_id INTEGER,
                workspace_id INTEGER,
                collection_id INTEGER,
                editor_id INTEGER,
                published_via TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scheduler_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                schedule_date TEXT,
                schedule_time TEXT,
                conflicting_schedule_ids TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workspace_timezones (
                workspace_id INTEGER PRIMARY KEY,
                timezone TEXT NOT NULL,
                updated_by INTEGER,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                read_at TEXT
            );

            CREATE TABLE IF NOT EXISTS central_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER,
                actor_role TEXT,
                action TEXT NOT NULL,
                module TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_retry_queue_next_attempt ON retry_queue(status, next_attempt_at, priority);
            CREATE INDEX IF NOT EXISTS idx_publish_history_channel ON publish_history(channel_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_publish_history_workspace ON publish_history(workspace_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at);
            CREATE INDEX IF NOT EXISTS idx_central_audit_module ON central_audit_log(module, created_at);
            """
        )


async def initialize() -> None:
    await asyncio.to_thread(_initialize_sync)


async def log_audit(
    *,
    actor_id: int | None,
    actor_role: str | None,
    action: str,
    module: str,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata_json: str | None = None,
) -> None:
    def _write() -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO central_audit_log(actor_id, actor_role, action, module, target_type, target_id, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (actor_id, actor_role, action, module, target_type, target_id, metadata_json, _now_iso()),
            )
            connection.commit()

    await asyncio.to_thread(_write)


async def create_notification(user_id: int, role: str, category: str, title: str, message: str) -> None:
    def _create() -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO notifications(user_id, role, category, title, message, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (user_id, role, category, title, message, _now_iso()),
            )
            connection.commit()

    await asyncio.to_thread(_create)


async def list_notifications(user_id: int, *, unread_only: bool = False, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))
    safe_offset = max(0, int(offset))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if unread_only:
                rows = connection.execute(
                    """
                    SELECT * FROM notifications
                    WHERE user_id = ? AND is_read = 0
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM notifications
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, safe_limit, safe_offset),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def mark_notifications_read(user_id: int) -> int:
    def _mark() -> int:
        with get_connection() as connection:
            cursor = connection.execute(
                "UPDATE notifications SET is_read = 1, read_at = ? WHERE user_id = ? AND is_read = 0",
                (_now_iso(), user_id),
            )
            connection.commit()
            return int(cursor.rowcount)

    return await asyncio.to_thread(_mark)


async def detect_schedule_conflict(channel_id: int, schedule_date: str, schedule_time: str) -> list[int]:
    """Return conflicting schedule ids for exact channel/date/time match."""

    def _detect() -> list[int]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id FROM scheduled_posts
                WHERE channel_id = ? AND schedule_date = ? AND schedule_time = ? AND status IN ('pending', 'active')
                ORDER BY id
                """,
                (channel_id, schedule_date, schedule_time),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                connection.execute(
                    """
                    INSERT INTO scheduler_conflicts(channel_id, schedule_date, schedule_time, conflicting_schedule_ids, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (channel_id, schedule_date, schedule_time, ",".join(str(i) for i in ids), _now_iso()),
                )
                connection.commit()
            return ids

    return await asyncio.to_thread(_detect)


async def set_workspace_timezone(workspace_id: int, timezone_name: str, updated_by: int | None = None) -> bool:
    tz = (timezone_name or "").strip()
    if not tz:
        return False

    def _set() -> bool:
        with get_connection() as connection:
            ws = connection.execute("SELECT workspace_id FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
            if ws is None:
                return False
            connection.execute(
                """
                INSERT INTO workspace_timezones(workspace_id, timezone, updated_by, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    timezone = excluded.timezone,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (workspace_id, tz, updated_by, _now_iso()),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_set)


async def get_workspace_timezone(workspace_id: int, default_timezone: str) -> str:
    def _get() -> str:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT timezone FROM workspace_timezones WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
            return str(row["timezone"]) if row is not None else default_timezone

    return await asyncio.to_thread(_get)


async def record_publish(
    *,
    draft_id: int | None,
    channel_id: int,
    workspace_id: int | None,
    collection_id: int | None,
    editor_id: int | None,
    published_via: str,
    status: str,
    error_message: str | None = None,
) -> None:
    def _record() -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO publish_history(draft_id, channel_id, workspace_id, collection_id, editor_id, published_via, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (draft_id, channel_id, workspace_id, collection_id, editor_id, published_via, status, error_message, _now_iso()),
            )
            connection.commit()

    await asyncio.to_thread(_record)


async def enqueue_retry(
    *,
    schedule_id: int | None,
    draft_id: int | None,
    channel_id: int | None,
    workspace_id: int | None,
    retry_reason: str,
    priority: int = 5,
    attempt_count: int = 0,
    max_attempts: int = 5,
    delay_seconds: int = 60,
    last_error: str | None = None,
) -> dict[str, Any] | None:
    priority = max(1, min(10, int(priority)))
    max_attempts = max(1, min(20, int(max_attempts)))
    next_attempt = datetime.now(timezone.utc) + timedelta(seconds=max(1, int(delay_seconds)))

    def _enqueue() -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO retry_queue(
                    schedule_id, draft_id, channel_id, workspace_id, retry_reason,
                    priority, attempt_count, max_attempts, next_attempt_at,
                    last_error, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    schedule_id,
                    draft_id,
                    channel_id,
                    workspace_id,
                    retry_reason,
                    priority,
                    attempt_count,
                    max_attempts,
                    next_attempt.isoformat(),
                    last_error,
                    _now_iso(),
                    _now_iso(),
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM retry_queue WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return _row_to_dict(row) if row is not None else None

    return await asyncio.to_thread(_enqueue)


async def get_due_retries(limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))

    def _get() -> list[dict[str, Any]]:
        now = _now_iso()
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM retry_queue
                WHERE status = 'queued' AND next_attempt_at <= ?
                ORDER BY priority DESC, next_attempt_at ASC, id ASC
                LIMIT ?
                """,
                (now, safe_limit),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_get)


async def mark_retry_state(retry_id: int, status: str, *, attempt_count: int | None = None, last_error: str | None = None, delay_seconds: int | None = None) -> bool:
    def _mark() -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT * FROM retry_queue WHERE id = ?", (retry_id,)).fetchone()
            if row is None:
                return False
            next_attempt = row["next_attempt_at"]
            if delay_seconds is not None and status == "queued":
                next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=max(1, int(delay_seconds)))).isoformat()
            connection.execute(
                """
                UPDATE retry_queue
                SET status = ?,
                    attempt_count = ?,
                    last_error = ?,
                    next_attempt_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    int(attempt_count if attempt_count is not None else row["attempt_count"]),
                    last_error,
                    next_attempt,
                    _now_iso(),
                    retry_id,
                ),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_mark)


async def get_retry_statistics() -> dict[str, int]:
    def _stats() -> dict[str, int]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM retry_queue GROUP BY status"
            ).fetchall()
            stats = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}
            for row in rows:
                stats[str(row["status"])] = int(row["count"])
            return stats

    return await asyncio.to_thread(_stats)


async def list_retry_queue(limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))
    safe_offset = max(0, int(offset))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM retry_queue
                ORDER BY priority DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def list_audit_logs(module: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))
    safe_offset = max(0, int(offset))
    mod = (module or "").strip().lower()

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if mod:
                rows = connection.execute(
                    """
                    SELECT * FROM central_audit_log
                    WHERE lower(module) = ?
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (mod, safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM central_audit_log
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (safe_limit, safe_offset),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def analytics_snapshot(scope: str, *, admin_id: int | None = None, workspace_id: int | None = None, collection_id: int | None = None, destination_id: int | None = None, editor_id: int | None = None) -> dict[str, int]:
    """Return aggregate counters for owner/admin/workspace/collection/destination/editor scopes."""

    def _snap() -> dict[str, int]:
        with get_connection() as connection:
            result = {
                "destinations": 0,
                "drafts": 0,
                "schedules": 0,
                "published": 0,
                "failed": 0,
                "templates": 0,
                "media": 0,
                "collections": 0,
                "workspaces": 0,
                "editors": 0,
            }

            if scope == "owner":
                result["destinations"] = int(connection.execute("SELECT COUNT(*) c FROM channels").fetchone()["c"])
                result["drafts"] = int(connection.execute("SELECT COUNT(*) c FROM drafts").fetchone()["c"])
                result["schedules"] = int(connection.execute("SELECT COUNT(*) c FROM scheduled_posts").fetchone()["c"])
                result["published"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE status = 'published'").fetchone()["c"])
                result["failed"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE status = 'failed'").fetchone()["c"])
                result["templates"] = int(connection.execute("SELECT COUNT(*) c FROM templates WHERE status = 'active'").fetchone()["c"])
                result["media"] = int(connection.execute("SELECT COUNT(*) c FROM media_library").fetchone()["c"])
                result["collections"] = int(connection.execute("SELECT COUNT(*) c FROM collections WHERE status = 'active'").fetchone()["c"])
                result["workspaces"] = int(connection.execute("SELECT COUNT(*) c FROM workspaces WHERE status = 'active'").fetchone()["c"])
                result["editors"] = int(connection.execute("SELECT COUNT(*) c FROM editor_profiles WHERE status = 'active'").fetchone()["c"])
                return result

            if scope == "admin" and admin_id is not None:
                result["destinations"] = int(connection.execute("SELECT COUNT(*) c FROM destination_owners WHERE admin_id = ?", (admin_id,)).fetchone()["c"])
                result["workspaces"] = int(connection.execute("SELECT COUNT(*) c FROM workspaces WHERE admin_id = ? AND status = 'active'", (admin_id,)).fetchone()["c"])
                result["collections"] = int(connection.execute("SELECT COUNT(*) c FROM collections WHERE admin_id = ? AND status = 'active'", (admin_id,)).fetchone()["c"])
                result["templates"] = int(connection.execute("SELECT COUNT(*) c FROM templates WHERE admin_id = ? AND status = 'active'", (admin_id,)).fetchone()["c"])
                result["editors"] = int(connection.execute("SELECT COUNT(*) c FROM editor_profiles WHERE admin_id = ? AND status = 'active'", (admin_id,)).fetchone()["c"])
                result["published"] = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) c
                        FROM publish_history ph
                        JOIN destination_owners d ON d.channel_id = ph.channel_id
                        WHERE d.admin_id = ? AND ph.status = 'published'
                        """,
                        (admin_id,),
                    ).fetchone()["c"]
                )
                result["failed"] = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) c
                        FROM publish_history ph
                        JOIN destination_owners d ON d.channel_id = ph.channel_id
                        WHERE d.admin_id = ? AND ph.status = 'failed'
                        """,
                        (admin_id,),
                    ).fetchone()["c"]
                )
                return result

            if scope == "workspace" and workspace_id is not None:
                result["collections"] = int(connection.execute("SELECT COUNT(*) c FROM collections WHERE workspace_id = ? AND status = 'active'", (workspace_id,)).fetchone()["c"])
                result["templates"] = int(connection.execute("SELECT COUNT(*) c FROM templates WHERE workspace_id = ? AND status = 'active'", (workspace_id,)).fetchone()["c"])
                result["media"] = int(connection.execute("SELECT COUNT(*) c FROM media_library WHERE workspace_id = ?", (workspace_id,)).fetchone()["c"])
                result["published"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE workspace_id = ? AND status = 'published'", (workspace_id,)).fetchone()["c"])
                result["failed"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE workspace_id = ? AND status = 'failed'", (workspace_id,)).fetchone()["c"])
                return result

            if scope == "collection" and collection_id is not None:
                result["destinations"] = int(connection.execute("SELECT COUNT(*) c FROM collection_destinations WHERE collection_id = ?", (collection_id,)).fetchone()["c"])
                result["published"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE collection_id = ? AND status = 'published'", (collection_id,)).fetchone()["c"])
                result["failed"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE collection_id = ? AND status = 'failed'", (collection_id,)).fetchone()["c"])
                return result

            if scope == "destination" and destination_id is not None:
                result["published"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE channel_id = ? AND status = 'published'", (destination_id,)).fetchone()["c"])
                result["failed"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE channel_id = ? AND status = 'failed'", (destination_id,)).fetchone()["c"])
                return result

            if scope == "editor" and editor_id is not None:
                result["published"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE editor_id = ? AND status = 'published'", (editor_id,)).fetchone()["c"])
                result["failed"] = int(connection.execute("SELECT COUNT(*) c FROM publish_history WHERE editor_id = ? AND status = 'failed'", (editor_id,)).fetchone()["c"])
                return result

            return result

    return await asyncio.to_thread(_snap)


async def global_search_all(query: str, limit: int = 20, offset: int = 0) -> dict[str, list[dict[str, Any]]]:
    q = (query or "").strip().lower()
    safe_limit = max(1, min(200, int(limit)))
    safe_offset = max(0, int(offset))
    if not q:
        return {"audit": [], "notifications": [], "history": [], "retry": []}

    def _search() -> dict[str, list[dict[str, Any]]]:
        with get_connection() as connection:
            audit = connection.execute(
                """
                SELECT id, action, module, target_type, target_id, created_at
                FROM central_audit_log
                WHERE lower(action) LIKE ? OR lower(module) LIKE ? OR lower(coalesce(target_id, '')) LIKE ? OR lower(coalesce(metadata_json, '')) LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", safe_limit, safe_offset),
            ).fetchall()

            notifications = connection.execute(
                """
                SELECT id, user_id, role, category, title, message, created_at
                FROM notifications
                WHERE lower(category) LIKE ? OR lower(title) LIKE ? OR lower(message) LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%", safe_limit, safe_offset),
            ).fetchall()

            history = connection.execute(
                """
                SELECT id, channel_id, published_via, status, error_message, created_at
                FROM publish_history
                WHERE lower(published_via) LIKE ? OR lower(status) LIKE ? OR lower(coalesce(error_message, '')) LIKE ? OR cast(channel_id as text) LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", safe_limit, safe_offset),
            ).fetchall()

            retry = connection.execute(
                """
                SELECT id, schedule_id, retry_reason, status, attempt_count, max_attempts, next_attempt_at
                FROM retry_queue
                WHERE lower(retry_reason) LIKE ? OR lower(status) LIKE ? OR lower(coalesce(last_error, '')) LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%", safe_limit, safe_offset),
            ).fetchall()

            return {
                "audit": [_row_to_dict(r) for r in audit],
                "notifications": [_row_to_dict(r) for r in notifications],
                "history": [_row_to_dict(r) for r in history],
                "retry": [_row_to_dict(r) for r in retry],
            }

    return await asyncio.to_thread(_search)


async def run_maintenance() -> dict[str, int]:
    """Run cleanup + VACUUM to keep SQLite healthy."""

    def _maintain() -> dict[str, int]:
        with get_connection() as connection:
            # mark old completed retries for archival cleanup
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            deleted_retry = connection.execute(
                "DELETE FROM retry_queue WHERE status IN ('completed', 'failed') AND updated_at < ?",
                (cutoff,),
            ).rowcount
            deleted_notifications = connection.execute(
                "DELETE FROM notifications WHERE is_read = 1 AND read_at IS NOT NULL AND read_at < ?",
                (cutoff,),
            ).rowcount
            connection.commit()

        with get_connection() as vacuum_connection:
            vacuum_connection.execute("VACUUM")
            vacuum_connection.commit()

        return {"deleted_retry": int(deleted_retry), "deleted_notifications": int(deleted_notifications)}

    return await asyncio.to_thread(_maintain)
