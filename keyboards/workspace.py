"""Inline keyboard builders for workspace and collection navigation."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_workspace_manager_keyboard() -> InlineKeyboardMarkup:
    """Build workspace module action keyboard."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Create Workspace", callback_data="workspace:open_create")],
            [InlineKeyboardButton("📋 Workspaces", callback_data="workspace:open_list")],
            [InlineKeyboardButton("🔁 Switch Workspace", callback_data="workspace:open_switch")],
            [InlineKeyboardButton("📂 Collections", callback_data="workspace:open_collections")],
            [InlineKeyboardButton("🖼 Media Library", callback_data="workspace:open_media")],
            [InlineKeyboardButton("📝 Templates", callback_data="workspace:open_templates")],
            [InlineKeyboardButton("⬅ Back", callback_data="dashboard:home")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )


def build_workspace_list_keyboard(workspaces: list[dict], current_workspace_id: int | None) -> InlineKeyboardMarkup:
    """Build workspace selection keyboard with breadcrumbs."""
    rows: list[list[InlineKeyboardButton]] = []
    for ws in workspaces:
        ws_id = int(ws["workspace_id"])
        marker = "🟢 " if current_workspace_id == ws_id else ""
        rows.append([InlineKeyboardButton(f"{marker}{ws['workspace_name']}", callback_data=f"workspace:switch:{ws_id}")])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="dashboard:workspaces")])
    rows.append([InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")])
    return InlineKeyboardMarkup(rows)


def build_workspace_delete_confirm_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    """Build confirmation keyboard for workspace deletion."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"workspace:delete_yes:{workspace_id}")],
            [InlineKeyboardButton("⬅ Back", callback_data="workspace:delete_no")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )


def build_collection_delete_confirm_keyboard(collection_id: int) -> InlineKeyboardMarkup:
    """Build confirmation keyboard for collection deletion."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"collection:delete_yes:{collection_id}")],
            [InlineKeyboardButton("⬅ Back", callback_data="collection:delete_no")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )
