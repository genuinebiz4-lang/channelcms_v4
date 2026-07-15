"""Inline keyboard builders for Help Center screens."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_help_center_keyboard() -> InlineKeyboardMarkup:
    """Build primary Help Center sections."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Getting Started", callback_data="help:getting_started")],
            [InlineKeyboardButton("🏢 Workspace Guide", callback_data="help:workspace")],
            [InlineKeyboardButton("📢 Destination Guide", callback_data="help:destinations")],
            [InlineKeyboardButton("📝 Posts", callback_data="help:posts")],
            [InlineKeyboardButton("📅 Scheduler", callback_data="help:scheduler")],
            [InlineKeyboardButton("🖼 Media Library", callback_data="help:media")],
            [InlineKeyboardButton("📂 Collections", callback_data="help:collections")],
            [InlineKeyboardButton("📝 Templates", callback_data="help:templates")],
            [InlineKeyboardButton("👥 Team Management", callback_data="help:team")],
            [InlineKeyboardButton("📊 Analytics", callback_data="help:analytics")],
            [InlineKeyboardButton("💳 Subscription", callback_data="help:subscription")],
            [InlineKeyboardButton("💰 Payments", callback_data="help:payments")],
            [InlineKeyboardButton("❓ FAQ", callback_data="help:faq")],
            [InlineKeyboardButton("🔧 Troubleshooting", callback_data="help:troubleshooting")],
            [InlineKeyboardButton("📞 Contact Support", callback_data="help:support")],
            [InlineKeyboardButton("📄 Download User Manual", callback_data="help:manual")],
            [InlineKeyboardButton("⬅ Back", callback_data="dashboard:home")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )
