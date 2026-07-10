"""Permission helpers for ChannelCMS V4."""

from __future__ import annotations

from telegram import Update

from config import OWNER_ID


def is_owner(update: Update) -> bool:
    """Check whether the update sender is the configured owner."""
    user = update.effective_user
    return bool(user and OWNER_ID and user.id == OWNER_ID)
