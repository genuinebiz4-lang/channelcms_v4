"""Workspace management, collections, media library, templates, and global search handlers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from database.provisioning import audit_action, get_editor_profile
from database.settings import get_admin_for_user
from database.enterprise import get_workspace_timezone, set_workspace_timezone
from database.workspace import (
    create_collection,
    create_template,
    create_workspace,
    delete_media,
    get_current_workspace,
    get_template,
    get_workspace,
    get_workspace_destinations,
    global_search,
    list_collection_destinations,
    list_collections,
    list_editor_workspaces,
    list_templates,
    list_workspaces,
    remove_destination_from_collection,
    render_template_text,
    save_media,
    search_media,
    set_current_workspace,
    soft_delete_collection,
    soft_delete_template,
    soft_delete_workspace,
    update_template,
    update_workspace,
    add_destination_to_collection,
)
from handlers.post import publish_to_channel
from keyboards.workspace import (
    build_collection_delete_confirm_keyboard,
    build_workspace_manager_keyboard,
    build_workspace_delete_confirm_keyboard,
    build_workspace_list_keyboard,
)
from states import WAITING_MEDIA_UPLOAD, WAITING_WORKSPACE_NAME
from utils.logger import get_logger
from utils.permissions import ROLE_ADMIN, ROLE_EDITOR, can_publish_content, get_request_role, is_owner
from utils.telegram_safety import safe_edit_message

logger = get_logger(__name__)


async def workspace_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show workspace module quick actions from dashboard callback."""
    query = update.callback_query
    if query is None:
        return
    await safe_edit_message(
        query,
        "🏢 Workspace Manager\n\n"
        "Use buttons to manage workspaces, collections, media, and templates.\n"
        "Typing is only required for names or search inputs.",
        reply_markup=build_workspace_manager_keyboard(),
    )


async def workspace_open_create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open create-workspace prompt from button-first workspace menu."""
    query = update.callback_query
    if query is None:
        return
    context.user_data["workspace_state"] = WAITING_WORKSPACE_NAME
    await safe_edit_message(
        query,
        "Send workspace name now.\nOptional format: Workspace Name | description",
        reply_markup=build_workspace_manager_keyboard(),
    )


async def workspace_open_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open workspace list from callback route."""
    await workspaces_command(update, context)


async def workspace_open_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show workspace list and switch guidance from callback route."""
    await workspaces_command(update, context)


async def workspace_open_collections_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render collection summary from callback route."""
    await collections_command(update, context)


async def workspace_open_media_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render media summary from callback route."""
    await media_command(update, context)


async def workspace_open_templates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render templates summary from callback route."""
    await templates_command(update, context)


def _split_pipe(text: str) -> list[str]:
    return [p.strip() for p in (text or "").split("|")]


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


async def _resolve_admin_scope(update: Update, *, allow_owner: bool = True) -> int | None:
    user = update.effective_user
    if user is None:
        return None

    role = await get_request_role(update)
    if role == ROLE_ADMIN:
        return await get_admin_for_user(user.id)

    if allow_owner and is_owner(update):
        text = update.effective_message.text or ""
        parts = text.split()
        if len(parts) > 1:
            admin_id = _parse_int(parts[1])
            if admin_id:
                return admin_id
    return None


async def _resolve_workspace_context(update: Update, context: ContextTypes.DEFAULT_TYPE, *, require: bool = True) -> tuple[int | None, dict[str, Any] | None]:
    user = update.effective_user
    if user is None:
        return None, None

    role = await get_request_role(update)
    admin_id = await get_admin_for_user(user.id)
    if role == ROLE_ADMIN:
        if admin_id is None:
            return None, None
        ws = await get_current_workspace(user.id, admin_id)
        if require and ws is None:
            await update.effective_message.reply_text("No workspace selected. Use /createworkspace first.")
        return admin_id, ws

    if role == ROLE_EDITOR:
        if admin_id is None:
            return None, None
        ws = await get_current_workspace(user.id, admin_id)
        if ws is None:
            if require:
                await update.effective_message.reply_text("No workspace assigned. Ask your admin.")
            return admin_id, None
        allowed = await list_editor_workspaces(user.id, admin_id)
        allowed_ids = {int(item["workspace_id"]) for item in allowed}
        if int(ws["workspace_id"]) not in allowed_ids:
            if require:
                await update.effective_message.reply_text("Current workspace is not assigned to your editor account.")
            return admin_id, None
        return admin_id, ws

    if is_owner(update):
        text = update.effective_message.text or ""
        parts = text.split()
        if len(parts) < 3:
            if require:
                await update.effective_message.reply_text("Owner usage: command <admin_id> <...>")
            return None, None
        admin_id = _parse_int(parts[1])
        if not admin_id:
            return None, None
        ws = await get_current_workspace(user.id, admin_id)
        return admin_id, ws

    return None, None


async def create_workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create workspace under admin scope."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN and not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Admin can create workspaces.")
        return

    user = update.effective_user
    if user is None:
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        context.user_data["workspace_state"] = WAITING_WORKSPACE_NAME
        await update.effective_message.reply_text(
            "Send workspace name now.\n"
            "Optional format: Workspace Name | description"
        )
        return

    await _create_workspace_from_text(update, context, parts[1])


async def _create_workspace_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str) -> None:
    """Create and auto-select workspace from provided text payload."""
    payload = _split_pipe(raw_text)
    name = payload[0] if payload else ""
    description = payload[1] if len(payload) > 1 else None

    if not name.strip():
        await update.effective_message.reply_text(
            "Workspace name cannot be empty. Send a valid name."
        )
        context.user_data["workspace_state"] = WAITING_WORKSPACE_NAME
        return

    admin_id = await _resolve_admin_scope(update)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        context.user_data.pop("workspace_state", None)
        return

    ok, message, ws = await create_workspace(admin_id, name, description)
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        context.user_data["workspace_state"] = WAITING_WORKSPACE_NAME
        return

    user = update.effective_user
    if user is None:
        context.user_data.pop("workspace_state", None)
        return

    await set_current_workspace(user.id, admin_id, int(ws["workspace_id"]))
    await audit_action(user.id, "workspace_created", admin_id, {"workspace_id": ws["workspace_id"], "name": ws["workspace_name"]})
    logger.info("Workspace created admin=%s workspace=%s", admin_id, ws["workspace_id"])
    context.user_data.pop("workspace_state", None)
    await update.effective_message.reply_text(
        "✅ Workspace created successfully.\n"
        f"Name: {ws['workspace_name']}\n"
        f"Workspace ID: {ws['workspace_id']}\n"
        "Selected as current workspace."
    )


async def receive_workspace_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle follow-up workspace name input after /createworkspace."""
    message = update.effective_message
    if message is None:
        return

    text = (message.text or "").strip()
    if not text:
        await message.reply_text("Please send a workspace name.")
        return

    await _create_workspace_from_text(update, context, text)


async def workspaces_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List workspaces and show switch keyboard."""
    user = update.effective_user
    if user is None:
        return

    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    admin_id, current = await _resolve_workspace_context(update, context, require=False)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    if role == ROLE_EDITOR:
        rows = await list_editor_workspaces(user.id, admin_id)
    else:
        rows = await list_workspaces(admin_id)

    if not rows:
        await update.effective_message.reply_text("No workspaces found.")
        return

    lines = ["🗂 Workspaces"]
    for ws in rows:
        marker = "(current)" if current and int(current["workspace_id"]) == int(ws["workspace_id"]) else ""
        lines.append(f"\n#{ws['workspace_id']} {ws['workspace_name']} {marker}")

    keyboard = build_workspace_list_keyboard(rows, int(current["workspace_id"]) if current else None)
    await update.effective_message.reply_text("\n".join(lines), reply_markup=keyboard)


async def switch_workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch current workspace by id."""
    user = update.effective_user
    if user is None:
        return

    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    text = update.effective_message.text or ""
    parts = text.split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /switchworkspace <workspace_id>")
        return

    ws_id = _parse_int(parts[1])
    if not ws_id:
        await update.effective_message.reply_text("Workspace ID must be numeric.")
        return

    admin_id = await get_admin_for_user(user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    ws = await get_workspace(ws_id)
    if ws is None or int(ws["admin_id"]) != int(admin_id) or ws["status"] != "active":
        await update.effective_message.reply_text("Workspace not found in your scope.")
        return

    if role == ROLE_EDITOR:
        allowed = await list_editor_workspaces(user.id, admin_id)
        allowed_ids = {int(item["workspace_id"]) for item in allowed}
        if ws_id not in allowed_ids:
            await update.effective_message.reply_text("This workspace is not assigned to your editor account.")
            return

    ok = await set_current_workspace(user.id, admin_id, ws_id)
    if not ok:
        await update.effective_message.reply_text("Unable to switch workspace.")
        return

    await update.effective_message.reply_text(f"✅ Switched to workspace: {ws['workspace_name']}")


async def edit_workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit workspace name/description."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN and not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Admin can edit workspaces.")
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /editworkspace <workspace_id> | new name | optional description")
        return

    payload = _split_pipe(parts[1])
    if len(payload) < 2:
        await update.effective_message.reply_text("Usage: /editworkspace <workspace_id> | new name | optional description")
        return

    ws_id = _parse_int(payload[0])
    if not ws_id:
        await update.effective_message.reply_text("Workspace ID must be numeric.")
        return

    name = payload[1]
    desc = payload[2] if len(payload) > 2 else None

    ws = await get_workspace(ws_id)
    if ws is None:
        await update.effective_message.reply_text("Workspace not found.")
        return

    admin_id = await _resolve_admin_scope(update)
    if admin_id is None or int(ws["admin_id"]) != int(admin_id):
        await update.effective_message.reply_text("Workspace is outside your scope.")
        return

    ok = await update_workspace(ws_id, workspace_name=name, description=desc)
    if not ok:
        await update.effective_message.reply_text("Unable to update workspace. Name may already exist.")
        return

    await audit_action(int(update.effective_user.id), "workspace_updated", admin_id, {"workspace_id": ws_id})
    await update.effective_message.reply_text("✅ Workspace updated.")


async def delete_workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for workspace deletion confirmation."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN and not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Admin can delete workspaces.")
        return

    text = update.effective_message.text or ""
    parts = text.split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /deleteworkspace <workspace_id>")
        return

    ws_id = _parse_int(parts[1])
    if not ws_id:
        await update.effective_message.reply_text("Workspace ID must be numeric.")
        return

    ws = await get_workspace(ws_id)
    if ws is None:
        await update.effective_message.reply_text("Workspace not found.")
        return

    admin_id = await _resolve_admin_scope(update)
    if admin_id is None or int(ws["admin_id"]) != int(admin_id):
        await update.effective_message.reply_text("Workspace is outside your scope.")
        return

    await update.effective_message.reply_text(
        f"Delete workspace {ws['workspace_name']}?",
        reply_markup=build_workspace_delete_confirm_keyboard(ws_id),
    )


async def workspace_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, workspace_id: int) -> None:
    """Switch workspace from inline keyboard."""
    query = update.callback_query
    if query is None:
        return
    user = update.effective_user
    if user is None:
        await query.answer("Invalid session", show_alert=True)
        return

    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await query.answer("Access denied", show_alert=True)
        return

    admin_id = await get_admin_for_user(user.id)
    if admin_id is None:
        await query.answer("Admin scope missing", show_alert=True)
        return

    ws = await get_workspace(workspace_id)
    if ws is None or int(ws["admin_id"]) != int(admin_id) or ws["status"] != "active":
        await query.answer("Workspace not found", show_alert=True)
        return

    if role == ROLE_EDITOR:
        allowed = await list_editor_workspaces(user.id, admin_id)
        if workspace_id not in {int(item["workspace_id"]) for item in allowed}:
            await query.answer("Workspace not assigned", show_alert=True)
            return

    ok = await set_current_workspace(user.id, admin_id, workspace_id)
    if not ok:
        await query.answer("Switch failed", show_alert=True)
        return

    await safe_edit_message(query, f"✅ Switched to workspace: {ws['workspace_name']}")


async def workspace_delete_yes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, workspace_id: int) -> None:
    """Confirm workspace deletion."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN and not is_owner(update):
        await query.answer("Access denied", show_alert=True)
        return

    ws = await get_workspace(workspace_id)
    if ws is None:
        await query.answer("Workspace not found", show_alert=True)
        return

    admin_id = int(ws["admin_id"]) if is_owner(update) else await _resolve_admin_scope(update)
    if admin_id is None or int(ws["admin_id"]) != int(admin_id):
        await query.answer("Out of scope", show_alert=True)
        return

    ok = await soft_delete_workspace(workspace_id)
    if not ok:
        await safe_edit_message(query, "Workspace deletion failed.")
        return

    await audit_action(int(update.effective_user.id), "workspace_deleted", admin_id, {"workspace_id": workspace_id})
    logger.info("Workspace deleted: admin=%s workspace=%s", admin_id, workspace_id)
    await safe_edit_message(query, "🗑 Workspace deleted.")


async def workspace_delete_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel workspace deletion."""
    query = update.callback_query
    if query is None:
        return
    await safe_edit_message(query, "Workspace deletion cancelled.")


async def create_collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create collection in current workspace."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can create collections.")
        return

    admin_id, ws = await _resolve_workspace_context(update, context)
    if admin_id is None or ws is None:
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /createcollection Collection Name | optional description")
        return

    payload = _split_pipe(parts[1])
    name = payload[0] if payload else ""
    description = payload[1] if len(payload) > 1 else None

    ok, message, row = await create_collection(admin_id, int(ws["workspace_id"]), name, description)
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        return

    await audit_action(int(update.effective_user.id), "collection_created", admin_id, {"collection_id": row["collection_id"]})
    logger.info("Collection created: admin=%s workspace=%s collection=%s", admin_id, ws["workspace_id"], row["collection_id"])
    await update.effective_message.reply_text(f"✅ Collection created: {row['collection_name']} (ID: {row['collection_id']})")


async def collections_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List collections in current workspace."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    admin_id, ws = await _resolve_workspace_context(update, context)
    if admin_id is None or ws is None:
        return

    rows = await list_collections(admin_id, int(ws["workspace_id"]))
    if not rows:
        await update.effective_message.reply_text("No collections found in current workspace.")
        return

    lines = [f"📚 Collections in {ws['workspace_name']}"]
    for row in rows:
        lines.append(f"\n#{row['collection_id']} {row['collection_name']}")
    await update.effective_message.reply_text("\n".join(lines))


async def add_to_collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add destination to collection."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can modify collections.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 3:
        await update.effective_message.reply_text("Usage: /addtocollection <collection_id> <destination_id>")
        return

    collection_id = _parse_int(parts[1])
    destination_id = _parse_int(parts[2])
    if not collection_id or destination_id is None:
        await update.effective_message.reply_text("IDs must be numeric.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    ok, message = await add_destination_to_collection(admin_id, collection_id, destination_id)
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        return

    await audit_action(int(update.effective_user.id), "collection_destination_added", admin_id, {"collection_id": collection_id, "destination_id": destination_id})
    await update.effective_message.reply_text("✅ Destination added to collection.")


async def remove_from_collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove destination from collection."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can modify collections.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 3:
        await update.effective_message.reply_text("Usage: /removefromcollection <collection_id> <destination_id>")
        return

    collection_id = _parse_int(parts[1])
    destination_id = _parse_int(parts[2])
    if not collection_id or destination_id is None:
        await update.effective_message.reply_text("IDs must be numeric.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    ok = await remove_destination_from_collection(admin_id, collection_id, destination_id)
    if not ok:
        await update.effective_message.reply_text("Destination or collection not found in scope.")
        return

    await audit_action(int(update.effective_user.id), "collection_destination_removed", admin_id, {"collection_id": collection_id, "destination_id": destination_id})
    await update.effective_message.reply_text("✅ Destination removed from collection.")


async def delete_collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask confirmation for collection deletion."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can delete collections.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /deletecollection <collection_id>")
        return

    collection_id = _parse_int(parts[1])
    if not collection_id:
        await update.effective_message.reply_text("Collection ID must be numeric.")
        return

    await update.effective_message.reply_text(
        f"Delete collection #{collection_id}?",
        reply_markup=build_collection_delete_confirm_keyboard(collection_id),
    )


async def collection_delete_yes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, collection_id: int) -> None:
    """Confirm collection deletion."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await query.answer("Access denied", show_alert=True)
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await query.answer("Admin scope missing", show_alert=True)
        return

    ok = await soft_delete_collection(admin_id, collection_id)
    if not ok:
        await safe_edit_message(query, "Collection not found in your scope.")
        return

    await audit_action(int(update.effective_user.id), "collection_deleted", admin_id, {"collection_id": collection_id})
    logger.info("Collection deleted: admin=%s collection=%s", admin_id, collection_id)
    await safe_edit_message(query, "🗑 Collection deleted.")


async def collection_delete_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel collection deletion."""
    query = update.callback_query
    if query is None:
        return
    await safe_edit_message(query, "Collection deletion cancelled.")


async def media_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent media items from current workspace."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return

    rows = await search_media(int(ws["workspace_id"]), query=None, media_type=None, limit=20)
    if not rows:
        await update.effective_message.reply_text("Media library is empty in current workspace.")
        return

    lines = [f"🗃 Media Library - {ws['workspace_name']}"]
    for row in rows[:10]:
        lines.append(
            f"\n#{row['media_id']} {row['file_type']} | tags: {row.get('tags') or '-'} | created: {row['created_at'][:19]}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def upload_media_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Begin media upload flow for current workspace."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    parts = (update.effective_message.text or "").split(maxsplit=1)
    tags = parts[1].strip() if len(parts) > 1 else ""
    context.user_data["workspace_state"] = WAITING_MEDIA_UPLOAD
    context.user_data["pending_media_tags"] = tags
    await update.effective_message.reply_text(
        "Send media now (photo/video/document/animation/voice/audio/sticker). Caption will be stored automatically."
    )


def _extract_media_payload(message: Any) -> tuple[str | None, str | None, str | None]:
    """Extract Telegram file payload as file_id, type, caption."""
    caption = (message.caption or "").strip() or None
    if getattr(message, "photo", None):
        return message.photo[-1].file_id, "photo", caption
    if getattr(message, "video", None):
        return message.video.file_id, "video", caption
    if getattr(message, "document", None):
        return message.document.file_id, "document", caption
    if getattr(message, "animation", None):
        return message.animation.file_id, "animation", caption
    if getattr(message, "voice", None):
        return message.voice.file_id, "voice", caption
    if getattr(message, "audio", None):
        return message.audio.file_id, "audio", caption
    if getattr(message, "sticker", None):
        return message.sticker.file_id, "sticker", caption
    return None, None, caption


async def receive_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Persist uploaded media into workspace media library with dedupe."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        context.user_data.pop("workspace_state", None)
        return

    user = update.effective_user
    if user is None:
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        context.user_data.pop("workspace_state", None)
        return

    message = update.effective_message
    file_id, file_type, caption = _extract_media_payload(message)
    if not file_id or not file_type:
        await message.reply_text("❌ Unsupported media type. Use photo/video/document/animation/voice/audio/sticker.")
        return

    tags = context.user_data.get("pending_media_tags") or ""
    ok, result_message, row = await save_media(
        workspace_id=int(ws["workspace_id"]),
        file_id=file_id,
        file_type=file_type,
        caption=caption,
        tags=str(tags),
        created_by=int(user.id),
    )
    if not ok:
        await message.reply_text(f"❌ {result_message}")
        return

    await audit_action(int(user.id), "media_uploaded", int(user.id), {"workspace_id": ws["workspace_id"], "media_id": row.get("media_id")})
    logger.info("Media saved workspace=%s media=%s type=%s", ws["workspace_id"], row.get("media_id"), file_type)

    await message.reply_text(
        f"✅ {result_message}\nMedia ID: {row.get('media_id')}\nType: {row.get('file_type')}\nTags: {row.get('tags') or '-'}"
    )
    context.user_data.pop("workspace_state", None)
    context.user_data.pop("pending_media_tags", None)


async def search_media_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search media library by tags, caption, type, or date text."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""

    rows = await search_media(int(ws["workspace_id"]), query=query, limit=20)
    if not rows:
        await update.effective_message.reply_text("No media matches your query.")
        return

    lines = [f"🔎 Media Search Results ({len(rows)})"]
    for row in rows:
        lines.append(f"\n#{row['media_id']} {row['file_type']} | tags: {row.get('tags') or '-'} | {row.get('caption') or ''}")
    await update.effective_message.reply_text("\n".join(lines))


async def delete_media_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete media from current workspace library."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can delete media.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /deletemedia <media_id>")
        return

    media_id = _parse_int(parts[1])
    if not media_id:
        await update.effective_message.reply_text("Media ID must be numeric.")
        return

    ok = await delete_media(int(ws["workspace_id"]), media_id)
    if not ok:
        await update.effective_message.reply_text("Media not found in current workspace.")
        return

    await audit_action(int(update.effective_user.id), "media_deleted", int(update.effective_user.id), {"workspace_id": ws["workspace_id"], "media_id": media_id})
    await update.effective_message.reply_text("🗑 Media deleted.")


def _default_template_values(update: Update, workspace: dict[str, Any], collection_name: str | None, destination_id: int | None) -> dict[str, str]:
    """Build built-in template variable values."""
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "username": update.effective_user.username or "",
        "workspace": str(workspace.get("workspace_name") or ""),
        "collection": collection_name or "",
        "destination": str(destination_id or ""),
    }


async def create_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create template in current workspace."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can create templates.")
        return

    admin_id, ws = await _resolve_workspace_context(update, context)
    if admin_id is None or ws is None:
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /createtemplate Name | body with {date} {time} etc")
        return

    payload = _split_pipe(parts[1])
    if len(payload) < 2:
        await update.effective_message.reply_text("Usage: /createtemplate Name | body with {date} {time} etc")
        return

    name = payload[0]
    body = payload[1]

    variables = {
        "date": "",
        "time": "",
        "username": "",
        "workspace": "",
        "collection": "",
        "destination": "",
    }

    ok, message, row = await create_template(
        workspace_id=int(ws["workspace_id"]),
        admin_id=int(admin_id),
        template_name=name,
        body_text=body,
        media_file_id=None,
        buttons=None,
        created_by=int(update.effective_user.id),
        variables=variables,
    )
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        return

    await audit_action(int(update.effective_user.id), "template_created", int(admin_id), {"template_id": row["template_id"]})
    logger.info("Template created workspace=%s template=%s", ws["workspace_id"], row["template_id"])
    await update.effective_message.reply_text(f"✅ Template created: {row['template_name']} (ID: {row['template_id']})")


async def templates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List templates in current workspace."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    query = parts[1] if len(parts) > 1 else None

    rows = await list_templates(int(ws["workspace_id"]), query=query, limit=50)
    if not rows:
        await update.effective_message.reply_text("No templates found in current workspace.")
        return

    lines = [f"📄 Templates in {ws['workspace_name']}"]
    for row in rows:
        preview = (row.get("body_text") or "").replace("\n", " ")[:50]
        lines.append(f"\n#{row['template_id']} {row['template_name']} | {preview}")
    await update.effective_message.reply_text("\n".join(lines))


async def edit_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit template name/body."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can edit templates.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /edittemplate <template_id> | name | body")
        return

    payload = _split_pipe(parts[1])
    if len(payload) < 3:
        await update.effective_message.reply_text("Usage: /edittemplate <template_id> | name | body")
        return

    template_id = _parse_int(payload[0])
    if not template_id:
        await update.effective_message.reply_text("Template ID must be numeric.")
        return

    ok = await update_template(int(ws["workspace_id"]), template_id, template_name=payload[1], body_text=payload[2])
    if not ok:
        await update.effective_message.reply_text("Unable to update template. Check ID/name uniqueness.")
        return

    await audit_action(int(update.effective_user.id), "template_updated", int(update.effective_user.id), {"template_id": template_id})
    await update.effective_message.reply_text("✅ Template updated.")


async def delete_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Soft delete template from workspace."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can delete templates.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /deletetemplate <template_id>")
        return

    template_id = _parse_int(parts[1])
    if not template_id:
        await update.effective_message.reply_text("Template ID must be numeric.")
        return

    ok = await soft_delete_template(int(ws["workspace_id"]), template_id)
    if not ok:
        await update.effective_message.reply_text("Template not found in current workspace.")
        return

    await audit_action(int(update.effective_user.id), "template_deleted", int(update.effective_user.id), {"template_id": template_id})
    await update.effective_message.reply_text("🗑 Template deleted.")


async def apply_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render and preview template with variable replacement."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    admin_id, ws = await _resolve_workspace_context(update, context)
    if admin_id is None or ws is None:
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /applytemplate <template_id> [key=value ...]")
        return

    template_id = _parse_int(parts[1])
    if not template_id:
        await update.effective_message.reply_text("Template ID must be numeric.")
        return

    record = await get_template(int(ws["workspace_id"]), template_id)
    if record is None:
        await update.effective_message.reply_text("Template not found in current workspace.")
        return

    values = _default_template_values(update, ws, collection_name=None, destination_id=None)
    for token in parts[2:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key.strip()] = value.strip()

    rendered = render_template_text(record.get("body_text") or "", values)
    await audit_action(int(update.effective_user.id), "template_used", int(admin_id), {"template_id": template_id, "workspace_id": ws["workspace_id"]})
    await update.effective_message.reply_text(
        f"✅ Template Applied: {record.get('template_name')}\n\n{rendered}"
    )


async def search_global_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search across workspace, collections, media, templates, destinations, drafts, editors."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /searchglobal <query>")
        return

    query = parts[1].strip()
    admin_id = await _resolve_admin_scope(update)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    result = await global_search(admin_id, query, limit=10)
    await audit_action(int(update.effective_user.id), "search_executed", int(admin_id), {"query": query})

    lines = [
        "🔎 Global Search",
        f"Query: {query}",
        f"Workspaces: {len(result['workspaces'])}",
        f"Collections: {len(result['collections'])}",
        f"Media: {len(result['media'])}",
        f"Templates: {len(result['templates'])}",
        f"Destinations: {len(result['destinations'])}",
        f"Drafts: {len(result['drafts'])}",
        f"Editors: {len(result['editors'])}",
    ]
    await update.effective_message.reply_text("\n".join(lines))


async def publish_collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Publish latest draft to all destinations in a collection."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    if not await can_publish_content(update):
        await update.effective_message.reply_text("🚫 Publishing is blocked. Approval may be required.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /publishcollection <collection_id>")
        return

    collection_id = _parse_int(parts[1])
    if not collection_id:
        await update.effective_message.reply_text("Collection ID must be numeric.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    destination_ids = await list_collection_destinations(admin_id, collection_id)
    if role == ROLE_EDITOR:
        profile = await get_editor_profile(update.effective_user.id)
        allowed = set(profile.get("assigned_destinations") or []) if profile else set()
        destination_ids = [d for d in destination_ids if d in allowed]

    if not destination_ids:
        await update.effective_message.reply_text("No publishable destinations in this collection.")
        return

    published = 0
    for destination_id in sorted(set(destination_ids)):
        await publish_to_channel(update, context, int(destination_id))
        published += 1

    await update.effective_message.reply_text(f"✅ Publish attempted to {published} destination(s) in collection #{collection_id}.")


async def publish_workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Publish latest draft to all destinations in current workspace scope."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    if not await can_publish_content(update):
        await update.effective_message.reply_text("🚫 Publishing is blocked. Approval may be required.")
        return

    admin_id, ws = await _resolve_workspace_context(update, context)
    if admin_id is None or ws is None:
        return

    destination_ids = await get_workspace_destinations(admin_id, int(ws["workspace_id"]))
    if role == ROLE_EDITOR:
        profile = await get_editor_profile(update.effective_user.id)
        allowed = set(profile.get("assigned_destinations") or []) if profile else set()
        destination_ids = [d for d in destination_ids if d in allowed]

    if not destination_ids:
        await update.effective_message.reply_text("No publishable destinations in current workspace.")
        return

    published = 0
    for destination_id in sorted(set(destination_ids)):
        await publish_to_channel(update, context, int(destination_id))
        published += 1

    await update.effective_message.reply_text(f"✅ Publish attempted to {published} destination(s) in workspace {ws['workspace_name']}.")


async def workspace_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current timezone for the selected workspace."""
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return
    tz = await get_workspace_timezone(int(ws["workspace_id"]), "Asia/Kolkata")
    await update.effective_message.reply_text(f"🕒 Workspace timezone: {tz}")


async def set_workspace_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set timezone for selected workspace."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN and not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Admin can set workspace timezone.")
        return

    _admin_id, ws = await _resolve_workspace_context(update, context)
    if ws is None:
        return

    parts = (update.effective_message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /setworkspacetimezone <IANA timezone>")
        return

    timezone_name = parts[1].strip()
    ok = await set_workspace_timezone(int(ws["workspace_id"]), timezone_name, int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Unable to set timezone for current workspace.")
        return

    await update.effective_message.reply_text(f"✅ Workspace timezone updated to: {timezone_name}")


def register_workspace_handlers(application: Application) -> None:
    """Register Milestone 7 workspace commands."""
    application.add_handler(CommandHandler("createworkspace", create_workspace_command))
    application.add_handler(CommandHandler("workspaces", workspaces_command))
    application.add_handler(CommandHandler("editworkspace", edit_workspace_command))
    application.add_handler(CommandHandler("deleteworkspace", delete_workspace_command))
    application.add_handler(CommandHandler("switchworkspace", switch_workspace_command))

    application.add_handler(CommandHandler("createcollection", create_collection_command))
    application.add_handler(CommandHandler("collections", collections_command))
    application.add_handler(CommandHandler("addtocollection", add_to_collection_command))
    application.add_handler(CommandHandler("removefromcollection", remove_from_collection_command))
    application.add_handler(CommandHandler("deletecollection", delete_collection_command))

    application.add_handler(CommandHandler("media", media_command))
    application.add_handler(CommandHandler("uploadmedia", upload_media_command))
    application.add_handler(CommandHandler("searchmedia", search_media_command))
    application.add_handler(CommandHandler("deletemedia", delete_media_command))

    application.add_handler(CommandHandler("createtemplate", create_template_command))
    application.add_handler(CommandHandler("templates", templates_command))
    application.add_handler(CommandHandler("edittemplate", edit_template_command))
    application.add_handler(CommandHandler("deletetemplate", delete_template_command))
    application.add_handler(CommandHandler("applytemplate", apply_template_command))

    application.add_handler(CommandHandler("searchglobal", search_global_command))

    application.add_handler(CommandHandler("publishcollection", publish_collection_command))
    application.add_handler(CommandHandler("publishworkspace", publish_workspace_command))
    application.add_handler(CommandHandler("workspacetimezone", workspace_timezone_command))
    application.add_handler(CommandHandler("setworkspacetimezone", set_workspace_timezone_command))
