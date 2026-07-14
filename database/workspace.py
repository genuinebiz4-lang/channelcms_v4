"""Workspace, collection, media, template, and search persistence for Flowza v1.0.1."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from database.db import get_connection


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initialize_sync() -> None:
    """Create workspace module tables and indexes without recreating existing schema."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                workspace_name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS user_workspace_context (
                user_id INTEGER PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workspace_editor_assignments (
                workspace_id INTEGER NOT NULL,
                editor_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (workspace_id, editor_id)
            );

            CREATE TABLE IF NOT EXISTS collections (
                collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                collection_name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS collection_destinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                destination_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(collection_id, destination_id)
            );

            CREATE TABLE IF NOT EXISTS media_library (
                media_id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                caption TEXT,
                tags TEXT,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(workspace_id, file_id)
            );

            CREATE TABLE IF NOT EXISTS templates (
                template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                template_name TEXT NOT NULL,
                body_text TEXT,
                media_file_id TEXT,
                buttons_json TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(workspace_id, template_name)
            );

            CREATE TABLE IF NOT EXISTS template_variables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                variable_name TEXT NOT NULL,
                default_value TEXT,
                UNIQUE(template_id, variable_name)
            );

            CREATE INDEX IF NOT EXISTS idx_workspaces_admin ON workspaces(admin_id, status);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_admin_name ON workspaces(admin_id, workspace_name);
            CREATE INDEX IF NOT EXISTS idx_workspace_editor_assignments_editor ON workspace_editor_assignments(editor_id, admin_id);
            CREATE INDEX IF NOT EXISTS idx_collections_workspace ON collections(workspace_id, status);
            CREATE INDEX IF NOT EXISTS idx_collection_destinations_dest ON collection_destinations(destination_id);
            CREATE INDEX IF NOT EXISTS idx_media_library_workspace_type ON media_library(workspace_id, file_type);
            CREATE INDEX IF NOT EXISTS idx_templates_workspace_status ON templates(workspace_id, status);
            CREATE INDEX IF NOT EXISTS idx_template_variables_template ON template_variables(template_id);
            """
        )


async def initialize() -> None:
    await asyncio.to_thread(_initialize_sync)


async def create_workspace(admin_id: int, workspace_name: str, description: str | None = None) -> tuple[bool, str, dict[str, Any] | None]:
    """Create a workspace for an admin."""
    name = (workspace_name or "").strip()
    if not name:
        return False, "Workspace name cannot be empty.", None

    def _create() -> tuple[bool, str, dict[str, Any] | None]:
        with get_connection() as connection:
            existing = connection.execute(
                "SELECT workspace_id FROM workspaces WHERE admin_id = ? AND lower(workspace_name) = lower(?) AND status != 'deleted'",
                (admin_id, name),
            ).fetchone()
            if existing is not None:
                return False, "Workspace already exists.", None
            now = _now_iso()
            cursor = connection.execute(
                """
                INSERT INTO workspaces(admin_id, workspace_name, description, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (admin_id, name, (description or "").strip() or None, now, now),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (cursor.lastrowid,)).fetchone()
            return True, "Workspace created.", None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_create)


async def list_workspaces(admin_id: int, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    """List workspaces for one admin."""

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if include_inactive:
                rows = connection.execute(
                    "SELECT * FROM workspaces WHERE admin_id = ? ORDER BY workspace_name COLLATE NOCASE",
                    (admin_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM workspaces WHERE admin_id = ? AND status = 'active' ORDER BY workspace_name COLLATE NOCASE",
                    (admin_id,),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def get_workspace(workspace_id: int) -> dict[str, Any] | None:
    """Get one workspace by identifier."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def update_workspace(workspace_id: int, *, workspace_name: str | None = None, description: str | None = None) -> bool:
    """Update workspace fields."""

    def _update() -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
            if row is None:
                return False
            name = (workspace_name or row["workspace_name"] or "").strip()
            if not name:
                return False
            existing = connection.execute(
                "SELECT workspace_id FROM workspaces WHERE admin_id = ? AND lower(workspace_name) = lower(?) AND workspace_id != ? AND status != 'deleted'",
                (row["admin_id"], name, workspace_id),
            ).fetchone()
            if existing is not None:
                return False
            connection.execute(
                """
                UPDATE workspaces
                SET workspace_name = ?, description = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (name, (description if description is not None else row["description"]), _now_iso(), workspace_id),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_update)


async def soft_delete_workspace(workspace_id: int) -> bool:
    """Soft delete workspace and mark related rows inactive."""

    def _delete() -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT workspace_id FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
            if row is None:
                return False
            now = _now_iso()
            connection.execute(
                "UPDATE workspaces SET status = 'deleted', updated_at = ? WHERE workspace_id = ?",
                (now, workspace_id),
            )
            connection.execute(
                "UPDATE collections SET status = 'deleted', updated_at = ? WHERE workspace_id = ?",
                (now, workspace_id),
            )
            connection.execute(
                "UPDATE templates SET status = 'deleted', updated_at = ? WHERE workspace_id = ?",
                (now, workspace_id),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_delete)


async def set_current_workspace(user_id: int, admin_id: int, workspace_id: int) -> bool:
    """Set workspace context for a user."""

    def _set() -> bool:
        with get_connection() as connection:
            ws = connection.execute(
                "SELECT workspace_id FROM workspaces WHERE workspace_id = ? AND admin_id = ? AND status = 'active'",
                (workspace_id, admin_id),
            ).fetchone()
            if ws is None:
                return False
            connection.execute(
                """
                INSERT INTO user_workspace_context(user_id, admin_id, workspace_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    admin_id = excluded.admin_id,
                    workspace_id = excluded.workspace_id,
                    updated_at = excluded.updated_at
                """,
                (user_id, admin_id, workspace_id, _now_iso()),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_set)


async def get_current_workspace(user_id: int, admin_id: int) -> dict[str, Any] | None:
    """Return current workspace context for a user, with auto-fallback to first active workspace."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            ctx = connection.execute(
                "SELECT workspace_id FROM user_workspace_context WHERE user_id = ? AND admin_id = ?",
                (user_id, admin_id),
            ).fetchone()
            if ctx is not None:
                ws = connection.execute(
                    "SELECT * FROM workspaces WHERE workspace_id = ? AND admin_id = ? AND status = 'active'",
                    (ctx["workspace_id"], admin_id),
                ).fetchone()
                if ws is not None:
                    return _row_to_dict(ws)
            ws = connection.execute(
                "SELECT * FROM workspaces WHERE admin_id = ? AND status = 'active' ORDER BY workspace_name COLLATE NOCASE LIMIT 1",
                (admin_id,),
            ).fetchone()
            if ws is None:
                return None
            connection.execute(
                """
                INSERT INTO user_workspace_context(user_id, admin_id, workspace_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    admin_id = excluded.admin_id,
                    workspace_id = excluded.workspace_id,
                    updated_at = excluded.updated_at
                """,
                (user_id, admin_id, ws["workspace_id"], _now_iso()),
            )
            connection.commit()
            return _row_to_dict(ws)

    return await asyncio.to_thread(_get)


async def assign_editor_workspace(editor_id: int, admin_id: int, workspace_id: int) -> bool:
    """Assign editor access to workspace."""

    def _assign() -> bool:
        with get_connection() as connection:
            ws = connection.execute(
                "SELECT workspace_id FROM workspaces WHERE workspace_id = ? AND admin_id = ? AND status = 'active'",
                (workspace_id, admin_id),
            ).fetchone()
            if ws is None:
                return False
            connection.execute(
                """
                INSERT INTO workspace_editor_assignments(workspace_id, editor_id, admin_id, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workspace_id, editor_id) DO NOTHING
                """,
                (workspace_id, editor_id, admin_id, _now_iso()),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_assign)


async def list_editor_workspaces(editor_id: int, admin_id: int) -> list[dict[str, Any]]:
    """List workspaces assigned to editor."""

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT w.*
                FROM workspaces w
                JOIN workspace_editor_assignments a ON a.workspace_id = w.workspace_id
                WHERE a.editor_id = ? AND a.admin_id = ? AND w.status = 'active'
                ORDER BY w.workspace_name COLLATE NOCASE
                """,
                (editor_id, admin_id),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def create_collection(admin_id: int, workspace_id: int, collection_name: str, description: str | None = None) -> tuple[bool, str, dict[str, Any] | None]:
    """Create destination collection inside workspace."""
    name = (collection_name or "").strip()
    if not name:
        return False, "Collection name cannot be empty.", None

    def _create() -> tuple[bool, str, dict[str, Any] | None]:
        with get_connection() as connection:
            ws = connection.execute(
                "SELECT workspace_id FROM workspaces WHERE workspace_id = ? AND admin_id = ? AND status = 'active'",
                (workspace_id, admin_id),
            ).fetchone()
            if ws is None:
                return False, "Workspace not found in your scope.", None
            exists = connection.execute(
                "SELECT collection_id FROM collections WHERE workspace_id = ? AND lower(collection_name)=lower(?) AND status != 'deleted'",
                (workspace_id, name),
            ).fetchone()
            if exists is not None:
                return False, "Collection already exists.", None
            now = _now_iso()
            cursor = connection.execute(
                """
                INSERT INTO collections(workspace_id, admin_id, collection_name, description, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
                """,
                (workspace_id, admin_id, name, (description or "").strip() or None, now, now),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM collections WHERE collection_id = ?", (cursor.lastrowid,)).fetchone()
            return True, "Collection created.", None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_create)


async def list_collections(admin_id: int, workspace_id: int) -> list[dict[str, Any]]:
    """List collections in workspace."""

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM collections
                WHERE admin_id = ? AND workspace_id = ? AND status = 'active'
                ORDER BY collection_name COLLATE NOCASE
                """,
                (admin_id, workspace_id),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def add_destination_to_collection(admin_id: int, collection_id: int, destination_id: int) -> tuple[bool, str]:
    """Attach destination to collection with ownership validation."""

    def _add() -> tuple[bool, str]:
        with get_connection() as connection:
            collection = connection.execute(
                "SELECT collection_id FROM collections WHERE collection_id = ? AND admin_id = ? AND status = 'active'",
                (collection_id, admin_id),
            ).fetchone()
            if collection is None:
                return False, "Collection not found in your scope."
            owner = connection.execute(
                "SELECT channel_id FROM destination_owners WHERE channel_id = ? AND admin_id = ?",
                (destination_id, admin_id),
            ).fetchone()
            if owner is None:
                return False, "Destination ownership validation failed."
            connection.execute(
                "INSERT OR IGNORE INTO collection_destinations(collection_id, destination_id, created_at) VALUES (?, ?, ?)",
                (collection_id, destination_id, _now_iso()),
            )
            connection.commit()
            return True, "Destination added to collection."

    return await asyncio.to_thread(_add)


async def remove_destination_from_collection(admin_id: int, collection_id: int, destination_id: int) -> bool:
    """Detach destination from collection."""

    def _remove() -> bool:
        with get_connection() as connection:
            collection = connection.execute(
                "SELECT collection_id FROM collections WHERE collection_id = ? AND admin_id = ?",
                (collection_id, admin_id),
            ).fetchone()
            if collection is None:
                return False
            cursor = connection.execute(
                "DELETE FROM collection_destinations WHERE collection_id = ? AND destination_id = ?",
                (collection_id, destination_id),
            )
            connection.commit()
            return bool(cursor.rowcount)

    return await asyncio.to_thread(_remove)


async def soft_delete_collection(admin_id: int, collection_id: int) -> bool:
    """Soft delete collection and unlink its destinations."""

    def _delete() -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT collection_id FROM collections WHERE collection_id = ? AND admin_id = ?",
                (collection_id, admin_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "UPDATE collections SET status = 'deleted', updated_at = ? WHERE collection_id = ?",
                (_now_iso(), collection_id),
            )
            connection.execute("DELETE FROM collection_destinations WHERE collection_id = ?", (collection_id,))
            connection.commit()
            return True

    return await asyncio.to_thread(_delete)


async def list_collection_destinations(admin_id: int, collection_id: int) -> list[int]:
    """List destination ids under one collection."""

    def _list() -> list[int]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT cd.destination_id
                FROM collection_destinations cd
                JOIN collections c ON c.collection_id = cd.collection_id
                WHERE cd.collection_id = ? AND c.admin_id = ? AND c.status = 'active'
                ORDER BY cd.destination_id
                """,
                (collection_id, admin_id),
            ).fetchall()
            return [int(row["destination_id"]) for row in rows]

    return await asyncio.to_thread(_list)


async def get_workspace_destinations(admin_id: int, workspace_id: int) -> list[int]:
    """List destinations mapped to an admin workspace (admin scope fallback)."""

    def _get() -> list[int]:
        with get_connection() as connection:
            ws = connection.execute(
                "SELECT workspace_id FROM workspaces WHERE workspace_id = ? AND admin_id = ? AND status = 'active'",
                (workspace_id, admin_id),
            ).fetchone()
            if ws is None:
                return []
            rows = connection.execute(
                "SELECT channel_id FROM destination_owners WHERE admin_id = ? ORDER BY channel_id",
                (admin_id,),
            ).fetchall()
            return [int(row["channel_id"]) for row in rows]

    return await asyncio.to_thread(_get)


async def save_media(
    workspace_id: int,
    file_id: str,
    file_type: str,
    caption: str | None,
    tags: str | None,
    created_by: int,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Save or reuse media asset in workspace."""
    normalized_file_id = (file_id or "").strip()
    normalized_type = (file_type or "").strip().lower()
    if not normalized_file_id or not normalized_type:
        return False, "Invalid media payload.", None

    def _save() -> tuple[bool, str, dict[str, Any] | None]:
        with get_connection() as connection:
            existing = connection.execute(
                "SELECT * FROM media_library WHERE workspace_id = ? AND file_id = ?",
                (workspace_id, normalized_file_id),
            ).fetchone()
            if existing is not None:
                row = _row_to_dict(existing)
                return True, "Media reused from library.", row
            now = _now_iso()
            cursor = connection.execute(
                """
                INSERT INTO media_library(workspace_id, file_id, file_type, caption, tags, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    normalized_file_id,
                    normalized_type,
                    (caption or "").strip() or None,
                    (tags or "").strip() or None,
                    created_by,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM media_library WHERE media_id = ?", (cursor.lastrowid,)).fetchone()
            return True, "Media uploaded to library.", None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_save)


async def search_media(workspace_id: int, query: str | None = None, media_type: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Search media by tags/caption/type/date text matching."""
    safe_limit = max(1, min(200, int(limit)))
    q = (query or "").strip().lower()
    t = (media_type or "").strip().lower()

    def _search() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if q and t:
                rows = connection.execute(
                    """
                    SELECT * FROM media_library
                    WHERE workspace_id = ? AND file_type = ?
                      AND (
                        lower(coalesce(caption, '')) LIKE ?
                        OR lower(coalesce(tags, '')) LIKE ?
                        OR lower(created_at) LIKE ?
                        OR lower(file_id) LIKE ?
                      )
                    ORDER BY media_id DESC
                    LIMIT ?
                    """,
                    (workspace_id, t, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", safe_limit),
                ).fetchall()
            elif q:
                rows = connection.execute(
                    """
                    SELECT * FROM media_library
                    WHERE workspace_id = ?
                      AND (
                        lower(coalesce(caption, '')) LIKE ?
                        OR lower(coalesce(tags, '')) LIKE ?
                        OR lower(created_at) LIKE ?
                        OR lower(file_id) LIKE ?
                        OR lower(file_type) LIKE ?
                      )
                    ORDER BY media_id DESC
                    LIMIT ?
                    """,
                    (workspace_id, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", safe_limit),
                ).fetchall()
            elif t:
                rows = connection.execute(
                    "SELECT * FROM media_library WHERE workspace_id = ? AND file_type = ? ORDER BY media_id DESC LIMIT ?",
                    (workspace_id, t, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM media_library WHERE workspace_id = ? ORDER BY media_id DESC LIMIT ?",
                    (workspace_id, safe_limit),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_search)


async def delete_media(workspace_id: int, media_id: int) -> bool:
    """Delete one media item from workspace library."""

    def _delete() -> bool:
        with get_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM media_library WHERE workspace_id = ? AND media_id = ?",
                (workspace_id, media_id),
            )
            connection.commit()
            return bool(cursor.rowcount)

    return await asyncio.to_thread(_delete)


async def create_template(
    workspace_id: int,
    admin_id: int,
    template_name: str,
    body_text: str | None,
    media_file_id: str | None,
    buttons: list[dict[str, Any]] | None,
    created_by: int,
    variables: dict[str, str] | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Create reusable template in a workspace."""
    name = (template_name or "").strip()
    if not name:
        return False, "Template name cannot be empty.", None

    def _create() -> tuple[bool, str, dict[str, Any] | None]:
        with get_connection() as connection:
            exists = connection.execute(
                "SELECT template_id FROM templates WHERE workspace_id = ? AND lower(template_name)=lower(?) AND status != 'deleted'",
                (workspace_id, name),
            ).fetchone()
            if exists is not None:
                return False, "Template name already exists in this workspace.", None
            now = _now_iso()
            cursor = connection.execute(
                """
                INSERT INTO templates(
                    workspace_id, admin_id, template_name, body_text, media_file_id,
                    buttons_json, status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    workspace_id,
                    admin_id,
                    name,
                    (body_text or "").strip() or None,
                    (media_file_id or "").strip() or None,
                    json.dumps(buttons or []),
                    created_by,
                    now,
                    now,
                ),
            )
            template_id = int(cursor.lastrowid)
            if variables:
                for key, value in variables.items():
                    key_name = str(key).strip()
                    if not key_name:
                        continue
                    connection.execute(
                        "INSERT OR IGNORE INTO template_variables(template_id, variable_name, default_value) VALUES (?, ?, ?)",
                        (template_id, key_name, str(value) if value is not None else None),
                    )
            connection.commit()
            row = connection.execute("SELECT * FROM templates WHERE template_id = ?", (template_id,)).fetchone()
            return True, "Template created.", None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_create)


async def list_templates(workspace_id: int, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List templates within workspace with optional search."""
    safe_limit = max(1, min(200, int(limit)))
    q = (query or "").strip().lower()

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if q:
                rows = connection.execute(
                    """
                    SELECT * FROM templates
                    WHERE workspace_id = ? AND status = 'active'
                      AND (lower(template_name) LIKE ? OR lower(coalesce(body_text, '')) LIKE ?)
                    ORDER BY template_name COLLATE NOCASE
                    LIMIT ?
                    """,
                    (workspace_id, f"%{q}%", f"%{q}%", safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM templates
                    WHERE workspace_id = ? AND status = 'active'
                    ORDER BY template_name COLLATE NOCASE
                    LIMIT ?
                    """,
                    (workspace_id, safe_limit),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def get_template(workspace_id: int, template_id: int) -> dict[str, Any] | None:
    """Get one active template."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM templates WHERE workspace_id = ? AND template_id = ? AND status = 'active'",
                (workspace_id, template_id),
            ).fetchone()
            if row is None:
                return None
            record = _row_to_dict(row)
            variables = connection.execute(
                "SELECT variable_name, default_value FROM template_variables WHERE template_id = ?",
                (template_id,),
            ).fetchall()
            record["variables"] = [{"name": v["variable_name"], "default": v["default_value"]} for v in variables]
            return record

    return await asyncio.to_thread(_get)


async def update_template(workspace_id: int, template_id: int, *, template_name: str, body_text: str | None) -> bool:
    """Update template body/name."""
    name = (template_name or "").strip()
    if not name:
        return False

    def _update() -> bool:
        with get_connection() as connection:
            existing = connection.execute(
                "SELECT template_id FROM templates WHERE workspace_id = ? AND template_id = ? AND status = 'active'",
                (workspace_id, template_id),
            ).fetchone()
            if existing is None:
                return False
            duplicate = connection.execute(
                "SELECT template_id FROM templates WHERE workspace_id = ? AND lower(template_name)=lower(?) AND template_id != ? AND status = 'active'",
                (workspace_id, name, template_id),
            ).fetchone()
            if duplicate is not None:
                return False
            connection.execute(
                "UPDATE templates SET template_name = ?, body_text = ?, updated_at = ? WHERE template_id = ?",
                (name, (body_text or "").strip() or None, _now_iso(), template_id),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_update)


async def soft_delete_template(workspace_id: int, template_id: int) -> bool:
    """Soft delete template and remove variable bindings."""

    def _delete() -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT template_id FROM templates WHERE workspace_id = ? AND template_id = ? AND status = 'active'",
                (workspace_id, template_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "UPDATE templates SET status = 'deleted', updated_at = ? WHERE template_id = ?",
                (_now_iso(), template_id),
            )
            connection.execute("DELETE FROM template_variables WHERE template_id = ?", (template_id,))
            connection.commit()
            return True

    return await asyncio.to_thread(_delete)


def render_template_text(template_body: str, values: dict[str, str]) -> str:
    """Render a template body by replacing known variable placeholders."""
    output = template_body or ""
    for key, value in values.items():
        output = output.replace("{" + key + "}", value)
    return output


async def global_search(admin_id: int, query: str, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    """Search across templates, media, collections, workspaces, destinations, drafts, editors."""
    q = (query or "").strip().lower()
    if not q:
        return {
            "workspaces": [],
            "collections": [],
            "media": [],
            "templates": [],
            "destinations": [],
            "drafts": [],
            "editors": [],
        }

    safe_limit = max(1, min(50, int(limit)))

    def _search() -> dict[str, list[dict[str, Any]]]:
        with get_connection() as connection:
            workspaces = connection.execute(
                """
                SELECT workspace_id, workspace_name, description
                FROM workspaces
                WHERE admin_id = ? AND status = 'active'
                  AND (lower(workspace_name) LIKE ? OR lower(coalesce(description, '')) LIKE ?)
                LIMIT ?
                """,
                (admin_id, f"%{q}%", f"%{q}%", safe_limit),
            ).fetchall()

            collections = connection.execute(
                """
                SELECT collection_id, workspace_id, collection_name, description
                FROM collections
                WHERE admin_id = ? AND status = 'active'
                  AND (lower(collection_name) LIKE ? OR lower(coalesce(description, '')) LIKE ?)
                LIMIT ?
                """,
                (admin_id, f"%{q}%", f"%{q}%", safe_limit),
            ).fetchall()

            media = connection.execute(
                """
                SELECT m.media_id, m.workspace_id, m.file_type, m.caption, m.tags
                FROM media_library m
                JOIN workspaces w ON w.workspace_id = m.workspace_id
                WHERE w.admin_id = ?
                  AND (
                    lower(coalesce(m.caption, '')) LIKE ?
                    OR lower(coalesce(m.tags, '')) LIKE ?
                    OR lower(m.file_type) LIKE ?
                    OR lower(m.created_at) LIKE ?
                  )
                LIMIT ?
                """,
                (admin_id, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", safe_limit),
            ).fetchall()

            templates = connection.execute(
                """
                SELECT t.template_id, t.workspace_id, t.template_name, t.body_text
                FROM templates t
                JOIN workspaces w ON w.workspace_id = t.workspace_id
                WHERE w.admin_id = ? AND t.status = 'active'
                  AND (lower(t.template_name) LIKE ? OR lower(coalesce(t.body_text, '')) LIKE ?)
                LIMIT ?
                """,
                (admin_id, f"%{q}%", f"%{q}%", safe_limit),
            ).fetchall()

            destinations = connection.execute(
                """
                SELECT c.channel_id, c.title, c.username
                FROM channels c
                JOIN destination_owners d ON d.channel_id = c.channel_id
                WHERE d.admin_id = ?
                  AND (lower(coalesce(c.title, '')) LIKE ? OR lower(coalesce(c.username, '')) LIKE ? OR cast(c.channel_id as text) LIKE ?)
                LIMIT ?
                """,
                (admin_id, f"%{q}%", f"%{q}%", f"%{q}%", safe_limit),
            ).fetchall()

            drafts = connection.execute(
                """
                SELECT d.id, d.draft_type, d.text, d.caption, d.created_at
                FROM drafts d
                WHERE lower(coalesce(d.text, '')) LIKE ? OR lower(coalesce(d.caption, '')) LIKE ? OR lower(coalesce(d.draft_type, '')) LIKE ?
                ORDER BY d.id DESC
                LIMIT ?
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%", safe_limit),
            ).fetchall()

            editors = connection.execute(
                """
                SELECT editor_id, username, full_name, workspace, status
                FROM editor_profiles
                WHERE admin_id = ?
                  AND (
                    lower(coalesce(username, '')) LIKE ?
                    OR lower(coalesce(full_name, '')) LIKE ?
                    OR lower(coalesce(workspace, '')) LIKE ?
                    OR cast(editor_id as text) LIKE ?
                  )
                LIMIT ?
                """,
                (admin_id, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", safe_limit),
            ).fetchall()

            return {
                "workspaces": [_row_to_dict(r) for r in workspaces],
                "collections": [_row_to_dict(r) for r in collections],
                "media": [_row_to_dict(r) for r in media],
                "templates": [_row_to_dict(r) for r in templates],
                "destinations": [_row_to_dict(r) for r in destinations],
                "drafts": [_row_to_dict(r) for r in drafts],
                "editors": [_row_to_dict(r) for r in editors],
            }

    return await asyncio.to_thread(_search)
