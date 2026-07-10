"""Dashboard keyboard builders for ChannelCMS V4."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Create the startup dashboard keyboard."""
    buttons = [
        [InlineKeyboardButton("📢 Channels", callback_data="dashboard:channels")],
        [InlineKeyboardButton("📝 Posts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("⏰ Scheduler", callback_data="dashboard:scheduler")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="dashboard:settings")],
    ]
    return InlineKeyboardMarkup(buttons)
