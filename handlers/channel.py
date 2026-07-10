"""Channel management handlers for ChannelCMS V4."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from database.channels import (
    add_channel,
    channel_exists,
    delete_channel,
    get_channel,
    get_channels,
    get_default_channel,
    set_default_channel as persist_default_channel,
    total_channels,
)
from keyboards.channel import (
    build_channel_manager_keyboard,
    build_channel_selection_keyboard,
    build_remove_confirmation_keyboard,
)
from states import WAITING_CHANNEL_FORWARD
from utils.logger import get_logger
from utils.permissions import is_owner

logger = get_logger(__name__)


async def _send_or_edit(
    update: Update,
    text: str,
    keyboard=None,
    answer_text: str | None = None,
) -> None:
    """Reply to a normal message or edit a callback message."""
    query = update.callback_query
    if query is not None:
        await query.answer(answer_text or "")
        await query.edit_message_text(text, reply_markup=keyboard)
        return

    if update.effective_message is not None:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def channel_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the channel management dashboard."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can manage channels.", answer_text="Access denied")
        return

    default_channel = await get_default_channel()
    text = (
        "📢 Channel Management\n\n"
        f"Total Channels: {await total_channels()}\n"
        f"Default Channel: {default_channel.get('title') if default_channel else 'None'}\n\n"
        "Use the buttons below to add, review, or manage your channels."
    )
    await _send_or_edit(update, text, keyboard=build_channel_manager_keyboard())


async def add_channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask the user to forward a message from a channel."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can add channels.", answer_text="Access denied")
        return

    context.user_data["channel_state"] = WAITING_CHANNEL_FORWARD
    text = (
        "➕ Add Channel\n\n"
        "Forward any message from your Telegram channel to continue."
    )
    await _send_or_edit(update, text, keyboard=build_channel_manager_keyboard())


async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a forwarded channel message and save the channel."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can add channels.", answer_text="Access denied")
        return

    message = update.effective_message
    if message is None:
        return

    origin_chat = None
    if getattr(message, "forward_origin", None) is not None:
        origin_chat = getattr(message.forward_origin, "chat", None)
    if origin_chat is None:
        origin_chat = getattr(message, "sender_chat", None)

    if origin_chat is None or getattr(origin_chat, "type", None) != "channel":
        await message.reply_text("❌ Please forward a message from a Telegram channel only.")
        return

    channel_id = getattr(origin_chat, "id", None)
    if channel_id is None:
        await message.reply_text("Unable to read the channel details from that message.")
        return

    if await channel_exists(channel_id):
        await message.reply_text("⚠️ This channel has already been added.")
        context.user_data.pop("channel_state", None)
        return

    title = getattr(origin_chat, "title", None) or "Unnamed Channel"
    username = getattr(origin_chat, "username", None)
    invite_link = None
    description = None
    member_count = 0

    try:
        chat = await context.bot.get_chat(channel_id)
        if chat.type != "channel":
            await message.reply_text("❌ Only Telegram channels are supported.")
            context.user_data.pop("channel_state", None)
            return
        title = chat.title or title
        username = chat.username or username
        description = chat.description or None
        member_count = getattr(chat, "member_count", 0) or 0
        member = await context.bot.get_chat_member(channel_id, context.bot.id)
        is_admin = getattr(member, "status", None) == "administrator"
        can_post = getattr(member, "can_post_messages", False)
        if not is_admin or not can_post:
            await message.reply_text(
                "❌ I need to be an administrator of that channel and have post permission."
            )
            context.user_data.pop("channel_state", None)
            return
    except Exception as exc:
        logger.exception("Failed to validate channel %s: %s", channel_id, exc)
        await message.reply_text("❌ I could not verify that channel.")
        context.user_data.pop("channel_state", None)
        return

    try:
        invite_link = await context.bot.export_chat_invite_link(channel_id)
    except Exception:
        invite_link = None

    await add_channel(
        channel_id=channel_id,
        title=title,
        username=username,
        invite_link=invite_link,
        description=description,
        member_count=member_count,
    )
    context.user_data.pop("channel_state", None)
    logger.info("Channel added: %s", channel_id)
    await message.reply_text(
        f"✅ Channel Added Successfully\n\n"
        f"Title: {title}\n"
        f"Username: @{username or 'n/a'}\n"
        f"ID: {channel_id}"
    )


async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all configured channels."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can view channels.", answer_text="Access denied")
        return

    channels = await get_channels()
    default_channel = await get_default_channel()
    total = await total_channels()
    default_label = default_channel.get("title") if default_channel else "None"

    if not channels:
        text = "📋 No channels have been added yet."
    else:
        lines = [f"📋 Total Channels: {total}", f"⭐ Default Channel: {default_label}", ""]
        for channel in channels:
            marker = "⭐" if channel.get("is_default") else "•"
            username = f"@{channel.get('username')}" if channel.get("username") else "n/a"
            lines.append(
                f"{marker} {channel.get('title') or 'Unnamed Channel'}\n"
                f"Username: {username}\n"
                f"ID: {channel.get('channel_id')}"
            )
        text = "\n\n".join(lines)

    await _send_or_edit(update, text, keyboard=build_channel_manager_keyboard())


async def default_channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available channels for selection as the new default channel."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can change the default channel.", answer_text="Access denied")
        return

    channels = await get_channels()
    if not channels:
        await _send_or_edit(update, "No channels available yet.", keyboard=build_channel_manager_keyboard())
        return

    text = "⭐ Select the default channel."
    await _send_or_edit(
        update,
        text,
        keyboard=build_channel_selection_keyboard(channels, "channel:set_default"),
    )


async def set_default_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: int) -> None:
    """Set a channel as the default channel."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can change the default channel.", answer_text="Access denied")
        return

    success = await persist_default_channel(channel_id)
    channel = await get_channel(channel_id)
    if success and channel:
        title = channel.get("title") or channel.get("username") or f"Channel {channel_id}"
        logger.info("Default channel changed to %s", channel_id)
        await _send_or_edit(update, f"⭐ Default channel updated to {title}.", keyboard=build_channel_manager_keyboard())
        return

    await _send_or_edit(update, "Unable to update the default channel.", keyboard=build_channel_manager_keyboard())


async def remove_channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show channels available for removal."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can remove channels.", answer_text="Access denied")
        return

    channels = await get_channels()
    if not channels:
        await _send_or_edit(update, "No channels available to remove.", keyboard=build_channel_manager_keyboard())
        return

    text = "🗑 Select a channel to remove."
    await _send_or_edit(
        update,
        text,
        keyboard=build_channel_selection_keyboard(channels, "channel:remove_confirm"),
    )


async def remove_channel_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: int,
    confirmed: bool = False,
) -> None:
    """Ask for confirmation before deleting a channel, or delete it if confirmed."""
    if not is_owner(update):
        await _send_or_edit(update, "🚫 Only the owner can remove channels.", answer_text="Access denied")
        return

    channel = await get_channel(channel_id)
    if channel is None:
        await _send_or_edit(update, "That channel was not found.", keyboard=build_channel_manager_keyboard())
        return

    if not confirmed:
        title = channel.get("title") or channel.get("username") or f"Channel {channel_id}"
        await _send_or_edit(
            update,
            f"Delete {title}?",
            keyboard=build_remove_confirmation_keyboard(channel_id),
        )
        return

    deleted = await delete_channel(channel_id)
    if deleted:
        logger.info("Channel deleted: %s", channel_id)
        await _send_or_edit(update, "🗑 Channel removed successfully.", keyboard=build_channel_manager_keyboard())
        return

    await _send_or_edit(update, "Unable to remove that channel.", keyboard=build_channel_manager_keyboard())
