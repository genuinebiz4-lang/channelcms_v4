"""Message routing for ChannelCMS V4."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.channel import receive_channel
from states import WAITING_CHANNEL_FORWARD
from utils.logger import get_logger

logger = get_logger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle general incoming messages and channel-forward flows."""
    if update.effective_message is None:
        return

    if context.user_data.get("channel_state") == WAITING_CHANNEL_FORWARD:
        await receive_channel(update, context)
        return

    text = update.effective_message.text or ""
    if text.startswith("/"):
        return

    await update.effective_message.reply_text(
        "💬 Thanks for your message. ChannelCMS V4 is ready for future features."
    )
    logger.info("Handled plain text message from %s", update.effective_user.id)
