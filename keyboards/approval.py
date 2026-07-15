"""Inline keyboard builders for approval workflow actions."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_admin_approval_actions(queue_id: int) -> InlineKeyboardMarkup:
    """Build action buttons for admin approval handling."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Preview", callback_data=f"approval:preview:{queue_id}")],
            [InlineKeyboardButton("Approve & Publish", callback_data=f"approval:approve_now:{queue_id}")],
            [InlineKeyboardButton("Approve & Schedule", callback_data=f"approval:approve_schedule:{queue_id}")],
            [InlineKeyboardButton("Reject", callback_data=f"approval:reject:{queue_id}")],
            [InlineKeyboardButton("Edit", callback_data=f"approval:edit:{queue_id}")],
            [InlineKeyboardButton("⬅ Back", callback_data="dashboard:editor_approval")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )
