"""Start command handler for Flowza v1.0."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import APP_TITLE, VERSION
from database.settings import get_admin_for_user
from database.workspace import get_current_workspace
from utils.permissions import is_owner
from keyboards.dashboard import (
    build_admin_dashboard_keyboard,
    build_dashboard_keyboard,
    build_editor_dashboard_keyboard,
    build_first_run_keyboard,
    build_owner_dashboard_keyboard,
)
from utils.logger import get_logger
from utils.permissions import ROLE_ADMIN, ROLE_EDITOR, ROLE_OWNER, get_request_role
from utils.telegram_safety import safe_edit_message

logger = get_logger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the startup dashboard to the user."""
    await send_dashboard(update, context)


async def send_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render role-aware dashboard for command and callback entry points."""
    del context
    role = await get_request_role(update)

    user = update.effective_user
    if user is None:
        return

    if role == ROLE_ADMIN:
        admin_id = await get_admin_for_user(user.id)
        current_workspace = await get_current_workspace(user.id, int(admin_id)) if admin_id is not None else None
        if current_workspace is None:
            message = (
                f"🚀 {APP_TITLE} Setup Wizard\n\n"
                "Welcome to Flowza. Complete these steps to go live:\n"
                "1. Create Workspace\n"
                "2. Add Destination\n"
                "3. Create First Post\n"
                "4. Publish\n\n"
                f"Version: {VERSION}"
            )
            keyboard = build_first_run_keyboard()
            query = update.callback_query
            if query is not None:
                await query.answer()
                await safe_edit_message(query, message, reply_markup=keyboard)
            else:
                await update.effective_message.reply_text(message, reply_markup=keyboard)
            logger.info("Handled /start setup wizard for user %s", user.id)
            return

    admin_label = "System"
    workspace_label = "Not selected"
    if role == ROLE_ADMIN:
        admin_label = str(user.id)
        admin_id = await get_admin_for_user(user.id)
        if admin_id is not None:
            ws = await get_current_workspace(user.id, int(admin_id))
            if ws is not None:
                workspace_label = str(ws.get("workspace_name") or "Not selected")
    elif role == ROLE_EDITOR:
        admin_id = await get_admin_for_user(user.id)
        admin_label = str(admin_id) if admin_id is not None else "Unassigned"
        if admin_id is not None:
            ws = await get_current_workspace(user.id, int(admin_id))
            if ws is not None:
                workspace_label = str(ws.get("workspace_name") or "Not selected")
    elif is_owner(update):
        admin_label = "Owner"
        workspace_label = "Global"

    message = (
        "🚀 Welcome to Flowza\n\n"
        "Your Telegram Publishing Workspace\n\n"
        f"Workspace: {workspace_label}\n"
        f"Admin Name: {admin_label}\n"
        f"Role: {(role or 'guest').title()}\n"
        f"Version: {VERSION}"
    )
    if role == ROLE_OWNER:
        keyboard = build_owner_dashboard_keyboard()
    elif role == ROLE_ADMIN:
        keyboard = build_admin_dashboard_keyboard()
    elif role == ROLE_EDITOR:
        keyboard = build_editor_dashboard_keyboard()
    else:
        keyboard = build_dashboard_keyboard()
    query = update.callback_query
    if query is not None:
        await query.answer()
        await safe_edit_message(query, message, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(message, reply_markup=keyboard)
    logger.info("Handled /start for user %s", update.effective_user.id)


def register_start_handler(application: Application) -> None:
    """Register the /start command with the application."""
    application.add_handler(CommandHandler("start", start_command))
