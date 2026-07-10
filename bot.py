"""Entry point for the ChannelCMS V4 Telegram bot."""

from __future__ import annotations

import asyncio
import sys

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, MessageHandler, filters

from config import BOT_TOKEN
from database.channels import initialize as initialize_channels
from database.db import init_db
from handlers.start import register_start_handler
from routers.callback_router import handle_callback
from routers.message_router import handle_message
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def build_application() -> object | None:
    """Build the Telegram application and register handlers."""
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is not configured; bot will start in dry-run mode.")
        return None

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    register_start_handler(application)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    return application


def main() -> int:
    """Initialize the application and start the bot loop."""
    setup_logging()
    logger.info("Starting ChannelCMS V4")
    init_db()
    logger.info("SQLite database initialized")
    asyncio.run(initialize_channels())
    logger.info("Channel database initialized")

    application = build_application()
    if application is None:
        logger.info("Bot startup completed in dry-run mode.")
        return 0

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        application.run_polling(allowed_updates=["message", "callback_query"])
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    return 0


if __name__ == "__main__":
    sys.exit(main())
