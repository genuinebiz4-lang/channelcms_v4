"""Settings and role persistence for Flowza v1.0."""

from __future__ import annotations

import asyncio
from typing import Any

from database.db import get_connection

ALLOWED_ROLES = {"owner", "admin", "editor"}


def _row_to_dict(row: Any) -> dict[str, Any]:
	"""Convert a database row to a dictionary."""
	if row is None:
		return {}
	return dict(row)


def _initialize_sync() -> None:
	"""Create settings and RBAC tables if they do not already exist."""
	with get_connection() as connection:
		connection.executescript(
			"""
			CREATE TABLE IF NOT EXISTS user_roles (
				user_id INTEGER PRIMARY KEY,
				role TEXT NOT NULL CHECK(role IN ('owner', 'admin', 'editor')),
				admin_id INTEGER,
				is_active INTEGER NOT NULL DEFAULT 1,
				created_by INTEGER,
				created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
				updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			);

			CREATE TABLE IF NOT EXISTS admin_settings (
				admin_id INTEGER PRIMARY KEY,
				approval_required INTEGER NOT NULL DEFAULT 0,
				updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			);

			CREATE INDEX IF NOT EXISTS idx_user_roles_admin_id ON user_roles(admin_id);
			"""
		)


async def initialize() -> None:
	"""Initialize settings and role tables asynchronously."""
	await asyncio.to_thread(_initialize_sync)


async def assign_role(
	user_id: int,
	role: str,
	*,
	admin_id: int | None = None,
	created_by: int | None = None,
	is_active: bool = True,
) -> dict[str, Any] | None:
	"""Create or update a user role record."""
	normalized_role = (role or "").strip().lower()
	if user_id <= 0 or normalized_role not in ALLOWED_ROLES:
		return None

	if normalized_role == "editor" and not admin_id:
		return None

	if normalized_role in {"owner", "admin"}:
		admin_id = None

	def _assign() -> dict[str, Any] | None:
		with get_connection() as connection:
			connection.execute(
				"""
				INSERT INTO user_roles (user_id, role, admin_id, is_active, created_by)
				VALUES (?, ?, ?, ?, ?)
				ON CONFLICT(user_id) DO UPDATE SET
					role = excluded.role,
					admin_id = excluded.admin_id,
					is_active = excluded.is_active,
					created_by = excluded.created_by,
					updated_at = CURRENT_TIMESTAMP
				""",
				(user_id, normalized_role, admin_id, 1 if is_active else 0, created_by),
			)
			connection.commit()
			row = connection.execute(
				"SELECT * FROM user_roles WHERE user_id = ?",
				(user_id,),
			).fetchone()
			return None if row is None else _row_to_dict(row)

	return await asyncio.to_thread(_assign)


async def get_user(user_id: int) -> dict[str, Any] | None:
	"""Return a role record for a user, if available."""

	def _get() -> dict[str, Any] | None:
		with get_connection() as connection:
			row = connection.execute(
				"SELECT * FROM user_roles WHERE user_id = ? AND is_active = 1",
				(user_id,),
			).fetchone()
			return None if row is None else _row_to_dict(row)

	return await asyncio.to_thread(_get)


async def get_user_role(user_id: int) -> str | None:
	"""Return the effective role for a user."""
	user = await get_user(user_id)
	if user is None:
		return None
	return str(user.get("role") or "").strip().lower() or None


async def get_admin_for_user(user_id: int) -> int | None:
	"""Return the admin scope id for an admin/editor account."""
	user = await get_user(user_id)
	if user is None:
		return None

	role = str(user.get("role") or "").strip().lower()
	if role == "admin":
		return int(user_id)
	if role == "editor":
		admin_id = user.get("admin_id")
		return int(admin_id) if admin_id else None
	return None


async def list_editors(admin_id: int) -> list[dict[str, Any]]:
	"""List active editors assigned to a specific admin."""

	def _list() -> list[dict[str, Any]]:
		with get_connection() as connection:
			rows = connection.execute(
				"""
				SELECT * FROM user_roles
				WHERE role = 'editor' AND admin_id = ? AND is_active = 1
				ORDER BY updated_at DESC
				""",
				(admin_id,),
			).fetchall()
			return [_row_to_dict(row) for row in rows]

	return await asyncio.to_thread(_list)


async def set_approval_required(admin_id: int, required: bool) -> bool:
	"""Enable or disable approval workflow for an admin scope."""

	def _set() -> bool:
		with get_connection() as connection:
			connection.execute(
				"""
				INSERT INTO admin_settings (admin_id, approval_required)
				VALUES (?, ?)
				ON CONFLICT(admin_id) DO UPDATE SET
					approval_required = excluded.approval_required,
					updated_at = CURRENT_TIMESTAMP
				""",
				(admin_id, 1 if required else 0),
			)
			connection.commit()
			return True

	return await asyncio.to_thread(_set)


async def is_approval_required(admin_id: int) -> bool:
	"""Return whether approval workflow is enabled for an admin scope."""

	def _get() -> bool:
		with get_connection() as connection:
			row = connection.execute(
				"SELECT approval_required FROM admin_settings WHERE admin_id = ?",
				(admin_id,),
			).fetchone()
			if row is None:
				return False
			return bool(row["approval_required"])

	return await asyncio.to_thread(_get)
