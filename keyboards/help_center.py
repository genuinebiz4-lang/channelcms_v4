"""Inline keyboard builders for Help Center screens."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_help_center_keyboard() -> InlineKeyboardMarkup:
    """Build primary Help Center sections."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Getting Started", callback_data="help:getting_started")],
            [InlineKeyboardButton("🏢 Workspaces", callback_data="help:workspace")],
            [InlineKeyboardButton("📢 Destinations", callback_data="help:destinations")],
            [InlineKeyboardButton("📝 Posts", callback_data="help:posts")],
            [InlineKeyboardButton("📅 Scheduler", callback_data="help:scheduler")],
            [InlineKeyboardButton("🖼 Media Library", callback_data="help:media")],
            [InlineKeyboardButton("📂 Collections", callback_data="help:collections")],
            [InlineKeyboardButton("📝 Templates", callback_data="help:templates")],
            [InlineKeyboardButton("👥 Team", callback_data="help:team")],
            [InlineKeyboardButton("📊 Analytics", callback_data="help:analytics")],
            [InlineKeyboardButton("⚙ Settings", callback_data="help:settings")],
            [InlineKeyboardButton("❓ FAQ", callback_data="help:faq")],
            [InlineKeyboardButton("📞 Contact Support", callback_data="help:support")],
            [InlineKeyboardButton("📄 Download User Manual", callback_data="help:manual")],
            [InlineKeyboardButton("⬅ Back", callback_data="dashboard:home")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )


def build_support_keyboard() -> InlineKeyboardMarkup:
    """Build support page keyboard with direct Telegram link."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Open Telegram Support", url="https://t.me/Lazy999000")],
            [InlineKeyboardButton("⬅ Back", callback_data="dashboard:help")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )
