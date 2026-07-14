"""Inline keyboard builders for provisioning workflows."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_add_admin_confirmation_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    """Build confirmation keyboard for admin creation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Admin", callback_data=f"provision:addadmin:confirm:{admin_id}")],
            [InlineKeyboardButton("Cancel", callback_data="provision:addadmin:cancel")],
        ]
    )


def build_add_editor_confirmation_keyboard(editor_id: int) -> InlineKeyboardMarkup:
    """Build confirmation keyboard for editor creation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Editor", callback_data=f"provision:addeditor:confirm:{editor_id}")],
            [InlineKeyboardButton("Cancel", callback_data="provision:addeditor:cancel")],
        ]
    )
