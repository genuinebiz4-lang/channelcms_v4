"""Start command handler for ChannelCMS V4."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from keyboards.dashboard import build_dashboard_keyboard
from utils.logger import get_logger

logger = get_logger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the startup dashboard to the user."""
    message = (
        "🚀 ChannelCMS V4\n\n"
        "Professional Telegram Channel Management System\n\n"
        "Version 4.0.0"
    )
    keyboard = build_dashboard_keyboard()
    await update.effective_message.reply_text(message, reply_markup=keyboard)
    logger.info("Handled /start for user %s", update.effective_user.id)


def register_start_handler(application: Application) -> None:
    """Register the /start command with the application."""
    application.add_handler(CommandHandler("start", start_command))
