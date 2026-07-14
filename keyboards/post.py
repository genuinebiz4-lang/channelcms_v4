"""Inline keyboard builders for the post composer module."""

from __future__ import annotations

from functools import lru_cache

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@lru_cache(maxsize=1)
def build_post_keyboard() -> InlineKeyboardMarkup:
    """Create the main post composer keyboard."""
    buttons = [
        [InlineKeyboardButton("📝 Text", callback_data="post:text")],
        [InlineKeyboardButton("🖼 Photo", callback_data="post:photo")],
        [InlineKeyboardButton("🎞 GIF", callback_data="post:gif")],
        [InlineKeyboardButton("🎥 Video", callback_data="post:video")],
        [InlineKeyboardButton("📄 Document", callback_data="post:document")],
        [InlineKeyboardButton("🖼 Album", callback_data="post:album")],
        [InlineKeyboardButton("👀 Preview", callback_data="post:preview")],
        [InlineKeyboardButton("🚀 Publish", callback_data="post:publish")],
        [InlineKeyboardButton("✏ Edit Draft", callback_data="post:edit")],
        [InlineKeyboardButton("🗑 Delete Draft", callback_data="post:delete")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:channels")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_publish_keyboard(channel_ids: list[int]) -> InlineKeyboardMarkup:
    """Create a keyboard for selecting a channel for publication."""
    buttons: list[list[InlineKeyboardButton]] = []
    for channel_id in channel_ids:
        buttons.append([InlineKeyboardButton(f"Channel {channel_id}", callback_data=f"post:channel:{channel_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="post:dashboard")])
    return InlineKeyboardMarkup(buttons)


@lru_cache(maxsize=1)
def build_preview_keyboard() -> InlineKeyboardMarkup:
    """Create a preview action keyboard."""
    buttons = [
        [InlineKeyboardButton("🚀 Publish", callback_data="post:publish")],
        [InlineKeyboardButton("✏ Edit Draft", callback_data="post:edit")],
        [InlineKeyboardButton("🗑 Delete Draft", callback_data="post:delete")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:channels")],
    ]
    return InlineKeyboardMarkup(buttons)
