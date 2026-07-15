"""Provisioning persistence layer for Flowza v1.0."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from database.db import get_connection

TRIAL_DAYS = 45
DEFAULT_EDITOR_PERMISSIONS = {
    "can_draft": True,
    "can_edit": True,
    "can_schedule": True,
    "can_upload_media": True,
    "can_delete_draft": False,
    "can_publish": False,
    "can_view_analytics": False,
}


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _initialize_sync() -> None:
    """Create provisioning tables and indexes if they do not exist."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS admin_profiles (
                admin_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                trial_start TEXT NOT NULL,
                trial_end TEXT NOT NULL,
                subscription_expiry TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                workspace_count INTEGER NOT NULL DEFAULT 1,
                destination_count INTEGER NOT NULL DEFAULT 0,
                editors_count INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS editor_profiles (
                editor_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT NOT NULL,
                admin_id INTEGER NOT NULL,
                workspace TEXT NOT NULL,
                assigned_destinations TEXT NOT NULL DEFAULT '[]',
                permissions_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS destination_owners (
                channel_id INTEGER PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS provisioning_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_editor_profiles_admin_id ON editor_profiles(admin_id);
            CREATE INDEX IF NOT EXISTS idx_provisioning_audit_action ON provisioning_audit(action);
            """
        )


async def initialize() -> None:
    await asyncio.to_thread(_initialize_sync)


async def audit_action(actor_id: int, action: str, target_user_id: int | None = None, details: dict[str, Any] | None = None) -> None:
    """Write a provisioning audit entry."""

    def _write() -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO provisioning_audit (actor_id, action, target_user_id, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (actor_id, action, target_user_id, json.dumps(details or {}), _utc_now().isoformat()),
            )
            connection.commit()

    await asyncio.to_thread(_write)


async def create_admin_profile(
    *,
    admin_id: int,
    username: str | None,
    full_name: str,
    actor_id: int,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Create an admin profile and role assignment with trial period."""

    def _create() -> tuple[bool, str, dict[str, Any] | None]:
        now = _utc_now()
        trial_end = now + timedelta(days=TRIAL_DAYS)
        with get_connection() as connection:
            existing_role = connection.execute(
                "SELECT role, admin_id FROM user_roles WHERE user_id = ?",
                (admin_id,),
            ).fetchone()
            if existing_role is not None:
                role = str(existing_role["role"])
                if role == "owner":
                    return False, "This user is already the platform owner.", None
                if role == "admin":
                    return False, "This user is already an admin.", None
                return False, "This user is already assigned as an editor.", None

            connection.execute(
                """
                INSERT INTO user_roles (user_id, role, admin_id, is_active, created_by)
                VALUES (?, 'admin', NULL, 1, ?)
                """,
                (admin_id, actor_id),
            )
            connection.execute(
                """
                INSERT INTO admin_profiles (
                    admin_id, username, full_name, created_at, trial_start, trial_end,
                    subscription_expiry, status, workspace_count, destination_count, editors_count, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'active', 1, 0, 0, ?)
                """,
                (
                    admin_id,
                    username,
                    full_name,
                    now.isoformat(),
                    now.isoformat(),
                    trial_end.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO admin_settings (admin_id, approval_required, updated_at)
                VALUES (?, 0, CURRENT_TIMESTAMP)
                ON CONFLICT(admin_id) DO NOTHING
                """,
                (admin_id,),
            )
            connection.commit()
            profile = connection.execute(
                "SELECT * FROM admin_profiles WHERE admin_id = ?",
                (admin_id,),
            ).fetchone()
            return True, "Admin profile created.", None if profile is None else _row_to_dict(profile)

    return await asyncio.to_thread(_create)


async def set_admin_status(admin_id: int, *, active: bool, actor_id: int) -> bool:
    """Suspend or activate an admin account."""

    def _set_status() -> bool:
        now = _utc_now().isoformat()
        with get_connection() as connection:
            role_row = connection.execute(
                "SELECT role FROM user_roles WHERE user_id = ?",
                (admin_id,),
            ).fetchone()
            if role_row is None or role_row["role"] != "admin":
                return False
            connection.execute(
                "UPDATE user_roles SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (1 if active else 0, admin_id),
            )
            connection.execute(
                "UPDATE admin_profiles SET status = ?, last_updated = ? WHERE admin_id = ?",
                ("active" if active else "suspended", now, admin_id),
            )
            if not active:
                connection.execute(
                    "UPDATE user_roles SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE role = 'editor' AND admin_id = ?",
                    (admin_id,),
                )
                connection.execute(
                    "UPDATE editor_profiles SET status = 'suspended', updated_at = ? WHERE admin_id = ?",
                    (now, admin_id),
                )
            connection.commit()
            return True

    ok = await asyncio.to_thread(_set_status)
    if ok:
        await audit_action(actor_id, "admin_activated" if active else "admin_suspended", admin_id)
    return ok


async def delete_admin(admin_id: int, actor_id: int) -> bool:
    """Delete admin, linked editors, and destination ownership mappings."""

    def _delete() -> bool:
        with get_connection() as connection:
            role_row = connection.execute(
                "SELECT role FROM user_roles WHERE user_id = ?",
                (admin_id,),
            ).fetchone()
            if role_row is None or role_row["role"] != "admin":
                return False

            editor_rows = connection.execute(
                "SELECT editor_id FROM editor_profiles WHERE admin_id = ?",
                (admin_id,),
            ).fetchall()
            for editor_row in editor_rows:
                connection.execute("DELETE FROM user_roles WHERE user_id = ?", (editor_row["editor_id"],))

            connection.execute("DELETE FROM editor_profiles WHERE admin_id = ?", (admin_id,))
            connection.execute("DELETE FROM destination_owners WHERE admin_id = ?", (admin_id,))
            connection.execute("DELETE FROM admin_settings WHERE admin_id = ?", (admin_id,))
            connection.execute("DELETE FROM admin_profiles WHERE admin_id = ?", (admin_id,))
            connection.execute("DELETE FROM user_roles WHERE user_id = ?", (admin_id,))
            connection.commit()
            return True

    ok = await asyncio.to_thread(_delete)
    if ok:
        await audit_action(actor_id, "admin_deleted", admin_id)
    return ok


async def get_admin_profile(admin_id: int) -> dict[str, Any] | None:
    """Return admin profile details."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM admin_profiles WHERE admin_id = ?",
                (admin_id,),
            ).fetchone()
            if row is None:
                return None
            profile = _row_to_dict(row)
            trial_end = profile.get("trial_end")
            days_left = 0
            if trial_end:
                try:
                    days_left = max(0, (datetime.fromisoformat(trial_end) - _utc_now()).days)
                except ValueError:
                    days_left = 0
            profile["trial_days_left"] = days_left
            return profile

    return await asyncio.to_thread(_get)


async def list_admin_profiles() -> list[dict[str, Any]]:
    """Return all admins ordered by creation date."""

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM admin_profiles ORDER BY created_at DESC"
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def assign_destination_owner(channel_id: int, admin_id: int) -> bool:
    """Assign destination ownership to an admin."""

    def _assign() -> bool:
        with get_connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO destination_owners (channel_id, admin_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET
                        admin_id = excluded.admin_id,
                        updated_at = excluded.updated_at
                    """,
                    (channel_id, admin_id, _utc_now().isoformat()),
                )
                connection.commit()
                return True
            except Exception:
                return False

    return await asyncio.to_thread(_assign)


async def transfer_destination_owner(channel_id: int, new_admin_id: int, actor_id: int) -> bool:
    """Transfer destination ownership to another admin."""

    def _transfer() -> bool:
        with get_connection() as connection:
            admin = connection.execute(
                "SELECT 1 FROM user_roles WHERE user_id = ? AND role = 'admin'",
                (new_admin_id,),
            ).fetchone()
            if admin is None:
                return False
            connection.execute(
                """
                INSERT INTO destination_owners (channel_id, admin_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    admin_id = excluded.admin_id,
                    updated_at = excluded.updated_at
                """,
                (channel_id, new_admin_id, _utc_now().isoformat()),
            )
            connection.commit()
            return True

    ok = await asyncio.to_thread(_transfer)
    if ok:
        await audit_action(actor_id, "destination_transferred", new_admin_id, {"channel_id": channel_id})
    return ok


async def list_destinations_for_admin(admin_id: int) -> list[int]:
    """Return destination channel ids assigned to an admin."""

    def _list() -> list[int]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT channel_id FROM destination_owners WHERE admin_id = ? ORDER BY channel_id",
                (admin_id,),
            ).fetchall()
            return [int(row["channel_id"]) for row in rows]

    return await asyncio.to_thread(_list)


async def create_editor_profile(
    *,
    editor_id: int,
    username: str | None,
    full_name: str,
    admin_id: int,
    workspace: str,
    destinations: list[int],
    permissions: dict[str, bool] | None,
    actor_id: int,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Create editor profile and role assignment."""

    normalized_permissions = dict(DEFAULT_EDITOR_PERMISSIONS)
    if permissions:
        normalized_permissions.update({k: bool(v) for k, v in permissions.items() if k in normalized_permissions})

    def _create() -> tuple[bool, str, dict[str, Any] | None]:
        now = _utc_now().isoformat()
        with get_connection() as connection:
            admin_role = connection.execute(
                "SELECT is_active FROM user_roles WHERE user_id = ? AND role = 'admin'",
                (admin_id,),
            ).fetchone()
            if admin_role is None:
                return False, "Admin profile was not found.", None
            if not bool(admin_role["is_active"]):
                return False, "Admin account is suspended.", None

            existing_role = connection.execute(
                "SELECT role, admin_id FROM user_roles WHERE user_id = ?",
                (editor_id,),
            ).fetchone()
            if existing_role is not None:
                role = str(existing_role["role"])
                if role == "owner":
                    return False, "Owner cannot be assigned as editor.", None
                if role == "admin":
                    return False, "Admin cannot be assigned as editor.", None
                existing_admin = existing_role["admin_id"]
                if role == "editor" and existing_admin and int(existing_admin) != admin_id:
                    return False, "Editor already belongs to another admin.", None
                if role == "editor" and existing_admin and int(existing_admin) == admin_id:
                    return False, "This user is already an editor under your admin account.", None

            connection.execute(
                """
                INSERT INTO user_roles (user_id, role, admin_id, is_active, created_by)
                VALUES (?, 'editor', ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    role = 'editor',
                    admin_id = excluded.admin_id,
                    is_active = 1,
                    created_by = excluded.created_by,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (editor_id, admin_id, actor_id),
            )

            connection.execute(
                """
                INSERT INTO editor_profiles (
                    editor_id, username, full_name, admin_id, workspace,
                    assigned_destinations, permissions_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(editor_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name,
                    admin_id = excluded.admin_id,
                    workspace = excluded.workspace,
                    assigned_destinations = excluded.assigned_destinations,
                    permissions_json = excluded.permissions_json,
                    status = 'active',
                    updated_at = excluded.updated_at
                """,
                (
                    editor_id,
                    username,
                    full_name,
                    admin_id,
                    workspace,
                    json.dumps(destinations),
                    json.dumps(normalized_permissions),
                    now,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM editor_profiles WHERE editor_id = ?",
                (editor_id,),
            ).fetchone()
            return True, "Editor profile created.", None if row is None else _row_to_dict(row)

    result = await asyncio.to_thread(_create)
    if result[0]:
        await audit_action(actor_id, "editor_created", editor_id, {"admin_id": admin_id, "workspace": workspace})
    return result


async def get_editor_profile(editor_id: int) -> dict[str, Any] | None:
    """Return editor profile details."""

    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM editor_profiles WHERE editor_id = ?",
                (editor_id,),
            ).fetchone()
            if row is None:
                return None
            profile = _row_to_dict(row)
            try:
                profile["assigned_destinations"] = json.loads(profile.get("assigned_destinations") or "[]")
            except json.JSONDecodeError:
                profile["assigned_destinations"] = []
            try:
                profile["permissions"] = json.loads(profile.get("permissions_json") or "{}")
            except json.JSONDecodeError:
                profile["permissions"] = {}
            return profile

    return await asyncio.to_thread(_get)


async def list_editor_profiles(admin_id: int) -> list[dict[str, Any]]:
    """Return all editor profiles for an admin."""

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM editor_profiles WHERE admin_id = ? ORDER BY created_at DESC",
                (admin_id,),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def list_editor_activity(admin_id: int, *, editor_id: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent audit entries for editors in the given admin scope."""

    safe_limit = max(1, min(100, int(limit)))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if editor_id is None:
                rows = connection.execute(
                    """
                    SELECT a.*
                    FROM provisioning_audit a
                    JOIN editor_profiles e ON e.editor_id = a.target_user_id
                    WHERE e.admin_id = ?
                    ORDER BY a.id DESC
                    LIMIT ?
                    """,
                    (admin_id, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT a.*
                    FROM provisioning_audit a
                    JOIN editor_profiles e ON e.editor_id = a.target_user_id
                    WHERE e.admin_id = ? AND e.editor_id = ?
                    ORDER BY a.id DESC
                    LIMIT ?
                    """,
                    (admin_id, editor_id, safe_limit),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def set_editor_status(editor_id: int, admin_id: int, *, active: bool, actor_id: int) -> bool:
    """Suspend or activate an editor under an admin."""

    def _set() -> bool:
        now = _utc_now().isoformat()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT editor_id FROM editor_profiles WHERE editor_id = ? AND admin_id = ?",
                (editor_id, admin_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "UPDATE editor_profiles SET status = ?, updated_at = ? WHERE editor_id = ?",
                ("active" if active else "suspended", now, editor_id),
            )
            connection.execute(
                "UPDATE user_roles SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND role = 'editor'",
                (1 if active else 0, editor_id),
            )
            connection.commit()
            return True

    ok = await asyncio.to_thread(_set)
    if ok:
        await audit_action(actor_id, "editor_activated" if active else "editor_suspended", editor_id, {"admin_id": admin_id})
    return ok


async def delete_editor(editor_id: int, admin_id: int, actor_id: int) -> bool:
    """Delete an editor under an admin scope."""

    def _delete() -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT editor_id FROM editor_profiles WHERE editor_id = ? AND admin_id = ?",
                (editor_id, admin_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM editor_profiles WHERE editor_id = ?", (editor_id,))
            connection.execute("DELETE FROM user_roles WHERE user_id = ? AND role = 'editor'", (editor_id,))
            connection.commit()
            return True

    ok = await asyncio.to_thread(_delete)
    if ok:
        await audit_action(actor_id, "editor_deleted", editor_id, {"admin_id": admin_id})
    return ok


async def set_editor_permission(editor_id: int, admin_id: int, permission: str, enabled: bool, actor_id: int) -> tuple[bool, str]:
    """Update one permission flag for an editor."""
    if permission not in DEFAULT_EDITOR_PERMISSIONS:
        return False, "Unsupported permission key."

    def _set() -> tuple[bool, str]:
        now = _utc_now().isoformat()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT permissions_json FROM editor_profiles WHERE editor_id = ? AND admin_id = ?",
                (editor_id, admin_id),
            ).fetchone()
            if row is None:
                return False, "Editor not found in your scope."
            current = json.loads(row["permissions_json"] or "{}")
            merged = dict(DEFAULT_EDITOR_PERMISSIONS)
            merged.update({k: bool(v) for k, v in current.items() if k in DEFAULT_EDITOR_PERMISSIONS})
            merged[permission] = enabled
            connection.execute(
                "UPDATE editor_profiles SET permissions_json = ?, updated_at = ? WHERE editor_id = ?",
                (json.dumps(merged), now, editor_id),
            )
            connection.commit()
            return True, "Permission updated successfully."

    ok, message = await asyncio.to_thread(_set)
    if ok:
        await audit_action(actor_id, "editor_permission_changed", editor_id, {"admin_id": admin_id, "permission": permission, "enabled": enabled})
    return ok, message


async def get_admin_dashboard_stats(admin_id: int) -> dict[str, Any]:
    """Build admin dashboard summary metrics."""

    def _stats() -> dict[str, Any]:
        with get_connection() as connection:
            admin = connection.execute(
                "SELECT * FROM admin_profiles WHERE admin_id = ?",
                (admin_id,),
            ).fetchone()
            if admin is None:
                return {}

            trial_days_left = 0
            try:
                trial_days_left = max(0, (datetime.fromisoformat(admin["trial_end"]) - _utc_now()).days)
            except Exception:
                trial_days_left = 0

            editor_count = connection.execute(
                "SELECT COUNT(*) AS c FROM editor_profiles WHERE admin_id = ? AND status = 'active'",
                (admin_id,),
            ).fetchone()["c"]
            destination_count = connection.execute(
                "SELECT COUNT(*) AS c FROM destination_owners WHERE admin_id = ?",
                (admin_id,),
            ).fetchone()["c"]
            workspace_count = connection.execute(
                "SELECT COUNT(DISTINCT workspace) AS c FROM editor_profiles WHERE admin_id = ?",
                (admin_id,),
            ).fetchone()["c"]
            scheduled_count = connection.execute(
                """
                SELECT COUNT(*) AS c
                FROM scheduled_posts s
                JOIN destination_owners d ON d.channel_id = s.channel_id
                WHERE d.admin_id = ?
                """,
                (admin_id,),
            ).fetchone()["c"]
            today_start = datetime.now().date().isoformat()
            published_today = connection.execute(
                """
                SELECT COUNT(*) AS c
                FROM scheduled_posts s
                JOIN destination_owners d ON d.channel_id = s.channel_id
                WHERE d.admin_id = ? AND s.status = 'completed' AND COALESCE(s.last_run, '') >= ?
                """,
                (admin_id, today_start),
            ).fetchone()["c"]

            return {
                "subscription_expiry": admin["subscription_expiry"],
                "trial_days_left": trial_days_left,
                "editors": int(editor_count),
                "destinations": int(destination_count),
                "workspaces": int(workspace_count),
                "scheduled_posts": int(scheduled_count),
                "published_today": int(published_today),
                "status": admin["status"],
            }

    return await asyncio.to_thread(_stats)
