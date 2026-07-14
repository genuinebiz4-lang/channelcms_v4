"""Analytics, search, and audit handlers for Flowza v1.0.2."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from database.enterprise import analytics_snapshot, global_search_all
from database.settings import get_admin_for_user
from database.workspace import get_current_workspace
from utils.permissions import ROLE_ADMIN, ROLE_EDITOR, get_request_role, is_owner


def _kv_lines(title: str, data: dict[str, int]) -> str:
    lines = [title]
    for key, value in data.items():
        lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    return "\n".join(lines)


async def owner_analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only owner can view this analytics scope.")
        return
    snapshot = await analytics_snapshot("owner")
    await update.effective_message.reply_text(_kv_lines("📊 Owner Analytics", snapshot))


async def admin_analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    snapshot = await analytics_snapshot("admin", admin_id=int(admin_id))
    await update.effective_message.reply_text(_kv_lines("📊 Admin Analytics", snapshot))


async def workspace_analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    workspace = await get_current_workspace(update.effective_user.id, int(admin_id))
    if workspace is None:
        await update.effective_message.reply_text("No current workspace selected.")
        return

    snapshot = await analytics_snapshot("workspace", workspace_id=int(workspace["workspace_id"]))
    await update.effective_message.reply_text(_kv_lines(f"📊 Workspace Analytics ({workspace['workspace_name']})", snapshot))


async def collection_analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR}:
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /collectionanalytics <collection_id>")
        return

    try:
        collection_id = int(parts[1])
    except ValueError:
        await update.effective_message.reply_text("Collection ID must be numeric.")
        return

    snapshot = await analytics_snapshot("collection", collection_id=collection_id)
    await update.effective_message.reply_text(_kv_lines(f"📊 Collection Analytics #{collection_id}", snapshot))


async def destination_analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /destinationanalytics <channel_id>")
        return

    try:
        channel_id = int(parts[1])
    except ValueError:
        await update.effective_message.reply_text("Channel ID must be numeric.")
        return

    snapshot = await analytics_snapshot("destination", destination_id=channel_id)
    await update.effective_message.reply_text(_kv_lines(f"📊 Destination Analytics {channel_id}", snapshot))


async def editor_analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    parts = (update.effective_message.text or "").split()
    editor_id = update.effective_user.id
    if len(parts) >= 2:
        try:
            editor_id = int(parts[1])
        except ValueError:
            await update.effective_message.reply_text("Editor ID must be numeric.")
            return

    snapshot = await analytics_snapshot("editor", editor_id=editor_id)
    await update.effective_message.reply_text(_kv_lines(f"📊 Editor Analytics {editor_id}", snapshot))


async def search_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    parts = (update.effective_message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /searchall <query>")
        return

    query = parts[1].strip()
    result = await global_search_all(query)
    await update.effective_message.reply_text(
        "🔎 Enterprise Search\n"
        f"Query: {query}\n"
        f"Audit: {len(result['audit'])}\n"
        f"Notifications: {len(result['notifications'])}\n"
        f"Publish History: {len(result['history'])}\n"
        f"Retry Queue: {len(result['retry'])}"
    )


def register_analytics_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("owneranalytics", owner_analytics_command))
    application.add_handler(CommandHandler("adminanalytics", admin_analytics_command))
    application.add_handler(CommandHandler("workspaceanalytics", workspace_analytics_command))
    application.add_handler(CommandHandler("collectionanalytics", collection_analytics_command))
    application.add_handler(CommandHandler("destinationanalytics", destination_analytics_command))
    application.add_handler(CommandHandler("editoranalytics", editor_analytics_command))
    application.add_handler(CommandHandler("searchall", search_all_command))
