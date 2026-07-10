"""Callback query routing for ChannelCMS V4."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.channel import (
    add_channel_menu,
    channel_dashboard,
    default_channel_menu,
    list_channels,
    remove_channel_confirm,
    remove_channel_menu,
    set_default_channel,
)
from utils.logger import get_logger

logger = get_logger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callback queries."""
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    if data == "dashboard:channels":
        await query.answer()
        await channel_dashboard(update, context)
        return

    if data == "channel:dashboard":
        await query.answer()
        await channel_dashboard(update, context)
        return

    if data == "channel:add":
        await query.answer()
        await add_channel_menu(update, context)
        return

    if data == "channel:list":
        await query.answer()
        await list_channels(update, context)
        return

    if data == "channel:default_menu":
        await query.answer()
        await default_channel_menu(update, context)
        return

    if data == "channel:remove_menu":
        await query.answer()
        await remove_channel_menu(update, context)
        return

    if data == "channel:refresh":
        await query.answer()
        await channel_dashboard(update, context)
        return

    if data.startswith("channel:set_default:"):
        channel_id = int(data.split(":", 2)[-1])
        await query.answer()
        await set_default_channel(update, context, channel_id)
        return

    if data.startswith("channel:remove_confirm:"):
        channel_id = int(data.split(":", 2)[-1])
        await query.answer()
        await remove_channel_confirm(update, context, channel_id)
        return

    if data.startswith("channel:remove_yes:"):
        channel_id = int(data.split(":", 2)[-1])
        await query.answer()
        await remove_channel_confirm(update, context, channel_id, confirmed=True)
        return

    await query.answer("Unsupported action.")
