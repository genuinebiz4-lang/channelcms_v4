"""Inline keyboard builders for the scheduler module."""

from __future__ import annotations

from functools import lru_cache

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@lru_cache(maxsize=1)
def build_scheduler_keyboard() -> InlineKeyboardMarkup:
    """Create the main scheduler keyboard."""
    buttons = [
        [InlineKeyboardButton("📅 Schedule Post", callback_data="scheduler:schedule")],
        [InlineKeyboardButton("📆 Scheduled Posts", callback_data="scheduler:list")],
        [InlineKeyboardButton("⬅ Back", callback_data="dashboard:home")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_schedule_actions_keyboard(schedule_id: int) -> InlineKeyboardMarkup:
    """Create action buttons for an individual schedule."""
    buttons = [
        [InlineKeyboardButton("⏸ Pause", callback_data=f"scheduler:pause:{schedule_id}")],
        [InlineKeyboardButton("▶ Resume", callback_data=f"scheduler:resume:{schedule_id}")],
        [InlineKeyboardButton("✏ Edit", callback_data=f"scheduler:edit:{schedule_id}")],
        [InlineKeyboardButton("🗑 Delete", callback_data=f"scheduler:delete:{schedule_id}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="scheduler:list")],
        [InlineKeyboardButton("⬅ Back", callback_data="scheduler:list")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
    ]
    return InlineKeyboardMarkup(buttons)
