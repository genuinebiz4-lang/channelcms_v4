"""Entry point for the Flowza v1.0 Telegram bot."""

from __future__ import annotations

import asyncio
import sys

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import APP_TITLE, BOT_TOKEN, VERSION
from database.channels import initialize as initialize_channels
from database.db import init_db
from database.drafts import initialize as initialize_drafts
from database.provisioning import initialize as initialize_provisioning_db
from database.approval import initialize as initialize_approval_db
from database.workspace import initialize as initialize_workspace_db
from database.enterprise import initialize as initialize_enterprise_db
from database.scheduler import initialize as initialize_scheduler_db
from database.settings import initialize as initialize_settings_db
from handlers.analytics import register_analytics_handlers
from handlers.channel import register_channel_handlers
from handlers.notifications import register_notification_handlers
from handlers.approval import register_approval_handlers
from handlers.provisioning import register_provisioning_handlers
from handlers.workspace import register_workspace_handlers
from handlers.help_center import register_help_center_handlers
from handlers.scheduler import initialize_scheduler, retry_stats_command, shutdown_scheduler
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
    register_provisioning_handlers(application)
    register_approval_handlers(application)
    register_workspace_handlers(application)
    register_channel_handlers(application)
    register_help_center_handlers(application)
    register_analytics_handlers(application)
    register_notification_handlers(application)
    application.add_handler(CommandHandler("retrystats", retry_stats_command))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    return application


def main() -> int:
    """Initialize the application and start the bot loop."""
    setup_logging()
    logger.info("Starting %s", APP_TITLE)
    logger.info("Version: %s", VERSION)
    init_db()
    logger.info("SQLite database initialized")
    asyncio.run(initialize_channels())
    logger.info("Channel database initialized")
    asyncio.run(initialize_drafts())
    logger.info("Draft database initialized")
    asyncio.run(initialize_scheduler_db())
    logger.info("Scheduler database initialized")
    asyncio.run(initialize_settings_db())
    logger.info("Settings database initialized")
    asyncio.run(initialize_provisioning_db())
    logger.info("Provisioning database initialized")
    asyncio.run(initialize_approval_db())
    logger.info("Approval database initialized")
    asyncio.run(initialize_workspace_db())
    logger.info("Workspace database initialized")
    asyncio.run(initialize_enterprise_db())
    logger.info("Enterprise database initialized")

    application = build_application()
    if application is None:
        logger.info("Bot startup completed in dry-run mode.")
        return 0

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        initialize_scheduler(application)
        application.run_polling(allowed_updates=["message", "callback_query"])
    finally:
        shutdown_scheduler()
        loop.close()
        asyncio.set_event_loop(None)

    return 0


if __name__ == "__main__":
    sys.exit(main())
