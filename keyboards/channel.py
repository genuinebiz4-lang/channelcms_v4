"""Inline keyboard builders for the channel management module."""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_channel_manager_keyboard() -> InlineKeyboardMarkup:
    """Create the main channel management keyboard."""
    buttons = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="channel:add")],
        [InlineKeyboardButton("📋 My Channels", callback_data="channel:list")],
        [InlineKeyboardButton("⭐ Default Channel", callback_data="channel:default_menu")],
        [InlineKeyboardButton("🗑 Remove Channel", callback_data="channel:remove_menu")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="channel:refresh")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:channels")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_channel_selection_keyboard(
    channels: list[dict[str, Any]],
    callback_prefix: str,
) -> InlineKeyboardMarkup:
    """Create a keyboard listing available channels for selection."""
    buttons: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        label = channel.get("title") or channel.get("username") or f"Channel {channel.get('channel_id')}"
        callback_data = f"{callback_prefix}:{channel['channel_id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback_data)])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="channel:dashboard")])
    return InlineKeyboardMarkup(buttons)


def build_remove_confirmation_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    """Create the confirmation keyboard for channel removal."""
    buttons = [
        [InlineKeyboardButton("✅ Yes", callback_data=f"channel:remove_yes:{channel_id}")],
        [InlineKeyboardButton("❌ No", callback_data="channel:dashboard")],
    ]
    return InlineKeyboardMarkup(buttons)
