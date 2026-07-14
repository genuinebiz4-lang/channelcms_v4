"""Start command handler for Flowza v1.0."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import APP_TITLE, VERSION
from keyboards.dashboard import (
    build_admin_dashboard_keyboard,
    build_dashboard_keyboard,
    build_editor_dashboard_keyboard,
    build_owner_dashboard_keyboard,
)
from utils.logger import get_logger
from utils.permissions import ROLE_ADMIN, ROLE_EDITOR, ROLE_OWNER, get_request_role

logger = get_logger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the startup dashboard to the user."""
    del context
    role = await get_request_role(update)
    message = (
        f"🚀 {APP_TITLE}\n\n"
        "Professional Telegram Content Management System\n\n"
        "Automate.\n"
        "Schedule.\n"
        "Grow.\n\n"
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
    await update.effective_message.reply_text(message, reply_markup=keyboard)
    logger.info("Handled /start for user %s", update.effective_user.id)


def register_start_handler(application: Application) -> None:
    """Register the /start command with the application."""
    application.add_handler(CommandHandler("start", start_command))
